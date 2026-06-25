"""
app.py — 焊口管理系統 後端 (FastAPI)
提供 REST API 並以靜態檔提供前端 UI。
啟動: python app.py   →   http://127.0.0.1:8000
"""
import io
import os
import tempfile
import datetime
import webbrowser
import threading

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db
import importer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="焊口管理系統 API", version="1.0")


@app.on_event("startup")
def _startup():
    db.init_db()


# ============================================================
#  允許寫入的欄位(白名單,避免任意欄位注入)
# ============================================================
JOINT_COLS = {
    "drawing_id", "line_id", "joint_no", "size", "thickness", "schedule",
    "material", "weld_type_id", "joint_category", "db_factor", "db_count",
    "shop_field", "welding_process", "wps_id", "welder_root_id", "welder_cap_id",
    "fitup_by", "fitup_date", "weld_date", "heat_no", "nde_type", "nde_percent",
    "nde_date", "nde_result", "nde_report_no", "repair_count", "pwht_required",
    "pwht_done", "pwht_date", "test_package", "test_date", "test_result",
    "status", "subcontractor", "billing_period_id", "claim_status", "remark",
}
DRAWING_COLS = {
    "drawing_no", "serial_no", "line_id", "system_id", "size", "pipe_class",
    "sheet_index", "num_sheets", "current_rev", "rev_date", "scan_date",
    "status", "pdf_path", "remark",
}
SYSTEM_COLS = {"code", "name_zh", "pipe_class", "material", "color"}
WELDER_COLS = {"stamp", "name", "cert_no", "cert_expiry", "process", "active"}
WPS_COLS = {"wps_no", "process", "material_group", "thk_min", "thk_max", "remark"}
LINE_COLS = {"line_no", "system_id", "size", "pipe_class", "material", "medium",
             "od", "thickness", "design_temp", "design_press", "oper_temp",
             "oper_press", "insulation", "nde_req", "test_req", "pid_no", "remark"}
BILLING_COLS = {"code", "date_from", "date_to", "unit_price", "status", "note"}
ISSUE_COLS = {"weld_joint_id", "drawing_id", "issue_type", "description", "status"}
INSPECTION_COLS = {"weld_joint_id", "method", "percent", "request_date",
                   "inspect_date", "result", "report_no", "rt_drawing_no",
                   "inspector", "remark"}


def pick(payload, allowed):
    return {k: v for k, v in payload.items() if k in allowed}


def op(payload):
    return (payload or {}).get("_operator", "user")


# ============================================================
#  專案 Projects
# ============================================================
@app.get("/api/projects")
def list_projects():
    return db.query("SELECT * FROM project ORDER BY id DESC")


@app.post("/api/projects")
def create_project(payload: dict = Body(...)):
    data = pick(payload, {"code", "name", "owner", "contractor", "description", "status"})
    if not data.get("code") or not data.get("name"):
        raise HTTPException(400, "需要 code 與 name")
    if db.query_one("SELECT id FROM project WHERE code=?", (data["code"],)):
        raise HTTPException(409, "專案代號已存在")
    pid = db.insert("project", data, op(payload), f"建立專案 {data['code']}")
    db.seed_weld_types(pid)
    return db.query_one("SELECT * FROM project WHERE id=?", (pid,))


@app.put("/api/projects/{pid}")
def update_project(pid: int, payload: dict = Body(...)):
    db.update("project", pid, pick(payload, {"name", "owner", "contractor", "description", "status"}), op(payload))
    return db.query_one("SELECT * FROM project WHERE id=?", (pid,))


@app.delete("/api/projects/{pid}")
def delete_project(pid: int, operator: str = "user"):
    db.delete("project", pid, operator)
    return {"ok": True}


# ============================================================
#  儀表板 Dashboard
# ============================================================
@app.get("/api/projects/{pid}/dashboard")
def dashboard(pid: int):
    def one(sql, params=()):
        r = db.query_one(sql, params)
        return list(r.values())[0] if r else 0

    total = one("SELECT COUNT(*) c FROM weld_joint WHERE project_id=?", (pid,))
    welded = one("SELECT COUNT(*) c FROM weld_joint WHERE project_id=? AND weld_date IS NOT NULL", (pid,))
    db_total = one("SELECT COALESCE(SUM(db_count),0) FROM weld_joint WHERE project_id=?", (pid,))
    db_done = one("SELECT COALESCE(SUM(db_count),0) FROM weld_joint WHERE project_id=? AND weld_date IS NOT NULL", (pid,))

    by_status = db.query(
        "SELECT status, COUNT(*) n FROM weld_joint WHERE project_id=? GROUP BY status ORDER BY n DESC", (pid,))
    by_type = db.query(
        "SELECT COALESCE(wt.code,'(未填)') AS code, COUNT(*) n, "
        "SUM(CASE WHEN wj.weld_date IS NOT NULL THEN 1 ELSE 0 END) done "
        "FROM weld_joint wj LEFT JOIN weld_type wt ON wj.weld_type_id=wt.id "
        "WHERE wj.project_id=? GROUP BY wt.code ORDER BY n DESC", (pid,))
    by_system = db.query(
        "SELECT COALESCE(s.code,'(未分類)') AS code, COUNT(*) n, "
        "SUM(CASE WHEN wj.weld_date IS NOT NULL THEN 1 ELSE 0 END) done "
        "FROM weld_joint wj "
        "LEFT JOIN pipe_line pl ON wj.line_id=pl.id "
        "LEFT JOIN system s ON pl.system_id=s.id "
        "WHERE wj.project_id=? GROUP BY s.code ORDER BY n DESC", (pid,))
    by_billing = db.query(
        "SELECT COALESCE(bp.code,'(未指定)') AS code, COUNT(*) n, COALESCE(SUM(wj.db_count),0) db "
        "FROM weld_joint wj LEFT JOIN billing_period bp ON wj.billing_period_id=bp.id "
        "WHERE wj.project_id=? GROUP BY bp.code ORDER BY code", (pid,))

    rt_required = one("SELECT COUNT(*) FROM weld_joint WHERE project_id=? AND nde_type IS NOT NULL", (pid,))
    rt_done = one("SELECT COUNT(*) FROM weld_joint WHERE project_id=? AND nde_date IS NOT NULL", (pid,))
    rt_fail = one("SELECT COUNT(*) FROM weld_joint WHERE project_id=? AND nde_result='不合格'", (pid,))
    drawings = one("SELECT COUNT(*) FROM drawing WHERE project_id=?", (pid,))
    scanned = one("SELECT COUNT(*) FROM drawing WHERE project_id=? AND scan_date IS NOT NULL", (pid,))
    issues_open = one("SELECT COUNT(*) FROM joint_issue WHERE project_id=? AND status='待處理'", (pid,))

    return {
        "total_joints": total, "welded": welded,
        "pct": round(welded / total * 100, 1) if total else 0,
        "db_total": round(db_total, 1), "db_done": round(db_done, 1),
        "db_pct": round(db_done / db_total * 100, 1) if db_total else 0,
        "by_status": by_status, "by_type": by_type, "by_system": by_system,
        "by_billing": by_billing,
        "rt_required": rt_required, "rt_done": rt_done, "rt_fail": rt_fail,
        "rt_pass_pct": round((rt_done - rt_fail) / rt_done * 100, 1) if rt_done else 0,
        "drawings": drawings, "scanned": scanned, "issues_open": issues_open,
    }


# ============================================================
#  參考清單(下拉用)
# ============================================================
@app.get("/api/projects/{pid}/lookups")
def lookups(pid: int):
    return {
        "systems": db.query("SELECT id,code,name_zh FROM system WHERE project_id=? ORDER BY code", (pid,)),
        "weld_types": db.query("SELECT id,code,name FROM weld_type WHERE project_id=? ORDER BY code", (pid,)),
        "welders": db.query("SELECT id,stamp,name FROM welder WHERE project_id=? AND active=1 ORDER BY stamp", (pid,)),
        "wps": db.query("SELECT id,wps_no FROM wps WHERE project_id=? ORDER BY wps_no", (pid,)),
        "billing_periods": db.query("SELECT id,code,status FROM billing_period WHERE project_id=? ORDER BY code", (pid,)),
        "lines": db.query("SELECT id,line_no FROM pipe_line WHERE project_id=? ORDER BY line_no", (pid,)),
        "statuses": ["規劃", "組對", "完銲", "待檢", "合格", "不合格", "試壓", "完成"],
    }


# ============================================================
#  圖面 Drawings
# ============================================================
@app.get("/api/projects/{pid}/drawings")
def list_drawings(pid: int, q: str = "", limit: int = 500, offset: int = 0):
    where = "WHERE d.project_id=?"
    params = [pid]
    if q:
        where += " AND (d.drawing_no LIKE ? OR d.serial_no LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    rows = db.query(
        f"SELECT d.*, s.code AS system_code, pl.line_no, "
        f"(SELECT COUNT(*) FROM weld_joint wj WHERE wj.drawing_id=d.id) AS joint_count "
        f"FROM drawing d LEFT JOIN system s ON d.system_id=s.id "
        f"LEFT JOIN pipe_line pl ON d.line_id=pl.id {where} "
        f"ORDER BY d.serial_no, d.drawing_no LIMIT ? OFFSET ?", params + [limit, offset])
    total = db.query_one(f"SELECT COUNT(*) c FROM drawing d {where}", params)["c"]
    return {"rows": rows, "total": total}


@app.post("/api/projects/{pid}/drawings")
def create_drawing(pid: int, payload: dict = Body(...)):
    data = pick(payload, DRAWING_COLS)
    data["project_id"] = pid
    if not data.get("drawing_no"):
        raise HTTPException(400, "需要圖號")
    # 自動配流水號(若未填)
    if not data.get("serial_no"):
        nxt = db.query_one("SELECT COALESCE(MAX(CAST(serial_no AS INTEGER)),0)+1 n FROM drawing WHERE project_id=?", (pid,))
        data["serial_no"] = str(nxt["n"])
    try:
        did = db.insert("drawing", data, op(payload), f"新增圖面 {data['drawing_no']}")
    except Exception as e:
        raise HTTPException(409, f"圖號重複或錯誤:{e}")
    return db.query_one("SELECT * FROM drawing WHERE id=?", (did,))


@app.put("/api/drawings/{did}")
def update_drawing(did: int, payload: dict = Body(...)):
    db.update("drawing", did, pick(payload, DRAWING_COLS), op(payload))
    return db.query_one("SELECT * FROM drawing WHERE id=?", (did,))


@app.delete("/api/drawings/{did}")
def delete_drawing(did: int, operator: str = "user"):
    db.delete("drawing", did, operator)
    return {"ok": True}


# ============================================================
#  焊口 Weld Joints
# ============================================================
@app.get("/api/projects/{pid}/joints")
def list_joints(pid: int, q: str = "", status: str = "", system: str = "",
                drawing_id: int = 0, billing: str = "",
                limit: int = 200, offset: int = 0):
    where = "WHERE wj.project_id=?"
    params = [pid]
    if q:
        where += " AND (wj.joint_no LIKE ? OR d.drawing_no LIKE ? OR wj.material LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if status:
        where += " AND wj.status=?"; params.append(status)
    if drawing_id:
        where += " AND wj.drawing_id=?"; params.append(drawing_id)
    if system:
        where += " AND s.code=?"; params.append(system)
    if billing:
        where += " AND bp.code=?"; params.append(billing)
    base = (
        "FROM weld_joint wj "
        "LEFT JOIN drawing d ON wj.drawing_id=d.id "
        "LEFT JOIN pipe_line pl ON wj.line_id=pl.id "
        "LEFT JOIN system s ON pl.system_id=s.id "
        "LEFT JOIN weld_type wt ON wj.weld_type_id=wt.id "
        "LEFT JOIN billing_period bp ON wj.billing_period_id=bp.id "
        f"{where}")
    rows = db.query(
        "SELECT wj.id, wj.joint_no, wj.size, wj.thickness, wj.material, "
        "wj.shop_field, wj.weld_date, wj.status, wj.nde_type, wj.nde_result, "
        "wj.db_count, wj.claim_status, wj.remark, "
        "d.drawing_no, d.serial_no, s.code AS system_code, wt.code AS weld_type, "
        "bp.code AS billing_period "
        + base + " ORDER BY d.serial_no, wj.joint_no LIMIT ? OFFSET ?",
        params + [limit, offset])
    total = db.query_one("SELECT COUNT(*) c " + base, params)["c"]
    return {"rows": rows, "total": total}


@app.get("/api/joints/{jid}")
def get_joint(jid: int):
    j = db.query_one("SELECT * FROM weld_joint WHERE id=?", (jid,))
    if not j:
        raise HTTPException(404, "找不到焊口")
    j["inspections"] = db.query("SELECT * FROM inspection WHERE weld_joint_id=? ORDER BY id", (jid,))
    return j


@app.post("/api/projects/{pid}/joints")
def create_joint(pid: int, payload: dict = Body(...)):
    data = pick(payload, JOINT_COLS)
    data["project_id"] = pid
    if not data.get("joint_no"):
        raise HTTPException(400, "需要銲口編號")
    data.setdefault("status", "規劃")
    cols = ", ".join(data.keys())
    ph = ", ".join("?" for _ in data)
    try:
        jid = db.execute(f"INSERT INTO weld_joint ({cols}) VALUES ({ph})", tuple(data.values()))
    except Exception as e:
        raise HTTPException(409, f"焊口重複或錯誤:{e}")
    db.log(op(payload), "CREATE", "weld_joint", jid, f"新增焊口 {data.get('joint_no')}")
    return db.query_one("SELECT * FROM weld_joint WHERE id=?", (jid,))


@app.put("/api/joints/{jid}")
def update_joint(jid: int, payload: dict = Body(...)):
    data = pick(payload, JOINT_COLS)
    data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.update("weld_joint", jid, data, op(payload), f"更新焊口 #{jid}")
    return db.query_one("SELECT * FROM weld_joint WHERE id=?", (jid,))


@app.delete("/api/joints/{jid}")
def delete_joint(jid: int, operator: str = "user"):
    db.delete("weld_joint", jid, operator)
    return {"ok": True}


@app.post("/api/joints/{jid}/advance")
def advance_status(jid: int, payload: dict = Body(default={})):
    """快速推進狀態到下一階段。"""
    flow = ["規劃", "組對", "完銲", "待檢", "合格", "試壓", "完成"]
    j = db.query_one("SELECT status FROM weld_joint WHERE id=?", (jid,))
    if not j:
        raise HTTPException(404)
    cur = j["status"] or "規劃"
    nxt = flow[min(flow.index(cur) + 1, len(flow) - 1)] if cur in flow else "完銲"
    data = {"status": nxt, "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if nxt == "完銲" and not db.query_one("SELECT weld_date FROM weld_joint WHERE id=?", (jid,))["weld_date"]:
        data["weld_date"] = datetime.date.today().strftime("%Y-%m-%d")
    db.update("weld_joint", jid, data, op(payload), f"焊口 #{jid} 狀態 {cur}→{nxt}")
    return db.query_one("SELECT * FROM weld_joint WHERE id=?", (jid,))


# ============================================================
#  檢驗 Inspections
# ============================================================
@app.post("/api/joints/{jid}/inspections")
def add_inspection(jid: int, payload: dict = Body(...)):
    data = pick(payload, INSPECTION_COLS)
    data["weld_joint_id"] = jid
    cols = ", ".join(data.keys()); ph = ", ".join("?" for _ in data)
    iid = db.execute(f"INSERT INTO inspection ({cols}) VALUES ({ph})", tuple(data.values()))
    # 回寫摘要到焊口
    db.update("weld_joint", jid, {
        "nde_type": data.get("method"), "nde_date": data.get("inspect_date"),
        "nde_result": data.get("result"), "nde_report_no": data.get("report_no")},
        op(payload), f"焊口 #{jid} 新增檢驗 {data.get('method')}")
    return db.query_one("SELECT * FROM inspection WHERE id=?", (iid,))


# ============================================================
#  請款期別 Billing
# ============================================================
@app.get("/api/projects/{pid}/billing")
def list_billing(pid: int):
    return db.query(
        "SELECT bp.*, "
        "(SELECT COUNT(*) FROM weld_joint wj WHERE wj.billing_period_id=bp.id) joints, "
        "(SELECT COALESCE(SUM(db_count),0) FROM weld_joint wj WHERE wj.billing_period_id=bp.id) db "
        "FROM billing_period bp WHERE project_id=? ORDER BY code", (pid,))


@app.post("/api/projects/{pid}/billing")
def create_billing(pid: int, payload: dict = Body(...)):
    data = pick(payload, BILLING_COLS); data["project_id"] = pid
    if not data.get("code"):
        raise HTTPException(400, "需要期別代碼")
    try:
        bid = db.insert("billing_period", data, op(payload), f"新增請款期別 {data['code']}")
    except Exception as e:
        raise HTTPException(409, str(e))
    return db.query_one("SELECT * FROM billing_period WHERE id=?", (bid,))


@app.post("/api/projects/{pid}/billing/auto-assign")
def billing_auto_assign(pid: int, payload: dict = Body(default={})):
    """依完成日期(weld_date)所屬月份,自動把焊口歸入對應月份期別;期別不存在則建立。"""
    operator = op(payload)
    joints = db.query("SELECT id, weld_date FROM weld_joint WHERE project_id=? AND weld_date IS NOT NULL", (pid,))
    code_cache = {b["code"]: b["id"] for b in db.query("SELECT id,code FROM billing_period WHERE project_id=?", (pid,))}
    assigned = 0
    for j in joints:
        try:
            d = datetime.datetime.strptime(j["weld_date"][:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        code = d.strftime("%Y.%m")
        if code not in code_cache:
            code_cache[code] = db.execute(
                "INSERT INTO billing_period (project_id,code,date_from,date_to) VALUES (?,?,?,?)",
                (pid, code, d.replace(day=1).strftime("%Y-%m-%d"), code))
        db.execute("UPDATE weld_joint SET billing_period_id=? WHERE id=?", (code_cache[code], j["id"]))
        assigned += 1
    db.log(operator, "UPDATE", "billing_period", pid, f"自動歸期 {assigned} 個焊口")
    return {"assigned": assigned, "periods": len(code_cache)}


# ============================================================
#  問題焊口 Issues
# ============================================================
@app.get("/api/projects/{pid}/issues")
def list_issues(pid: int):
    return db.query(
        "SELECT i.*, wj.joint_no, d.drawing_no FROM joint_issue i "
        "LEFT JOIN weld_joint wj ON i.weld_joint_id=wj.id "
        "LEFT JOIN drawing d ON i.drawing_id=d.id "
        "WHERE i.project_id=? ORDER BY i.status, i.id DESC", (pid,))


@app.post("/api/projects/{pid}/issues")
def create_issue(pid: int, payload: dict = Body(...)):
    data = pick(payload, ISSUE_COLS); data["project_id"] = pid
    iid = db.insert("joint_issue", data, op(payload), f"新增問題:{data.get('issue_type')}")
    return db.query_one("SELECT * FROM joint_issue WHERE id=?", (iid,))


@app.put("/api/issues/{iid}")
def update_issue(iid: int, payload: dict = Body(...)):
    db.update("joint_issue", iid, pick(payload, ISSUE_COLS), op(payload))
    return db.query_one("SELECT * FROM joint_issue WHERE id=?", (iid,))


# ============================================================
#  焊工 / WPS / 系統 (基礎資料維護)
# ============================================================
def _crud_list(table, pid):
    return db.query(f"SELECT * FROM {table} WHERE project_id=? ORDER BY id", (pid,))


@app.get("/api/projects/{pid}/welders")
def list_welders(pid: int):
    return _crud_list("welder", pid)


@app.post("/api/projects/{pid}/welders")
def create_welder(pid: int, payload: dict = Body(...)):
    data = pick(payload, WELDER_COLS); data["project_id"] = pid
    wid = db.insert("welder", data, op(payload), f"新增焊工 {data.get('stamp')}")
    return db.query_one("SELECT * FROM welder WHERE id=?", (wid,))


@app.get("/api/projects/{pid}/wps")
def list_wps(pid: int):
    return _crud_list("wps", pid)


@app.post("/api/projects/{pid}/wps")
def create_wps(pid: int, payload: dict = Body(...)):
    data = pick(payload, WPS_COLS); data["project_id"] = pid
    wid = db.insert("wps", data, op(payload), f"新增 WPS {data.get('wps_no')}")
    return db.query_one("SELECT * FROM wps WHERE id=?", (wid,))


@app.get("/api/projects/{pid}/systems")
def list_systems(pid: int):
    return _crud_list("system", pid)


@app.post("/api/projects/{pid}/systems")
def create_system(pid: int, payload: dict = Body(...)):
    data = pick(payload, SYSTEM_COLS); data["project_id"] = pid
    sid = db.insert("system", data, op(payload), f"新增系統 {data.get('code')}")
    return db.query_one("SELECT * FROM system WHERE id=?", (sid,))


# ============================================================
#  稽核日誌 Audit
# ============================================================
@app.get("/api/audit")
def audit(limit: int = 200):
    return db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


# ============================================================
#  匯入 / 匯出 Excel
# ============================================================
@app.post("/api/import")
async def import_excel(file: UploadFile = File(...), code: str = Form(...),
                       name: str = Form(...), owner: str = Form(""),
                       operator: str = Form("user")):
    suffix = os.path.splitext(file.filename)[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read()); tmp.close()
        summary = importer.import_weld_control(tmp.name, code, name, owner or None, operator)
    except Exception as e:
        raise HTTPException(400, f"匯入失敗:{e}")
    finally:
        os.unlink(tmp.name)
    return summary


@app.get("/api/projects/{pid}/export/joints.xlsx")
def export_joints(pid: int):
    import openpyxl
    rows = db.query(
        "SELECT d.serial_no AS 流水號, d.drawing_no AS 圖號, wj.joint_no AS 銲口編號, "
        "wj.size AS 尺寸, wj.thickness AS 厚度, wj.material AS 材質, wt.code AS 銲接型式, "
        "wj.db_count AS DB數, wj.shop_field AS 預製現場, wj.weld_date AS 完成日期, "
        "wj.status AS 狀態, s.code AS 系統, wj.nde_type AS 檢驗, wj.nde_date AS 檢驗日期, "
        "wj.nde_result AS 檢驗結果, bp.code AS 請款期別, wj.claim_status AS 請款狀態, wj.remark AS 備註 "
        "FROM weld_joint wj LEFT JOIN drawing d ON wj.drawing_id=d.id "
        "LEFT JOIN pipe_line pl ON wj.line_id=pl.id LEFT JOIN system s ON pl.system_id=s.id "
        "LEFT JOIN weld_type wt ON wj.weld_type_id=wt.id "
        "LEFT JOIN billing_period bp ON wj.billing_period_id=bp.id "
        "WHERE wj.project_id=? ORDER BY d.serial_no, wj.joint_no", (pid,))
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "焊口明細"
    headers = list(rows[0].keys()) if rows else ["(無資料)"]
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    fname = f"joints_p{pid}_{datetime.date.today()}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"})


# ============================================================
#  前端靜態檔(放最後,讓 /api/* 優先)
# ============================================================
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")


def _open_browser():
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    import uvicorn
    threading.Timer(1.5, _open_browser).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
