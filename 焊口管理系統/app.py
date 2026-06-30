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
import sizes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="焊口管理系統 API", version="1.0")


@app.on_event("startup")
def _startup():
    db.init_db()


# ============================================================
#  允許寫入的欄位(白名單,避免任意欄位注入)
# ============================================================
JOINT_COLS = {
    "drawing_id", "line_id", "spool_id", "joint_no", "size", "thickness", "schedule",
    "material", "weld_type_id", "joint_category", "db_factor", "db_count",
    "shop_field", "welding_process", "wps_id", "welder_root_id", "welder_cap_id",
    "fitup_by", "fitup_date", "weld_date", "heat_no", "nde_type", "nde_percent",
    "nde_date", "nde_result", "nde_report_no", "repair_count", "pwht_required",
    "pwht_done", "pwht_date", "test_package", "test_package_id", "test_date", "test_result",
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
SPOOL_COLS = {"drawing_id", "spool_no", "shop_field", "status",
              "fab_dwg_no", "scan_date", "ship_date", "remark"}
HEAT_COLS = {"heat_no", "spec", "p_no", "size", "schedule",
             "mtr_no", "mtr_path", "pmi_done", "remark"}
FILLER_COLS = {"batch_no", "aws_class", "f_no", "spec", "bake_log", "remark"}
JMAT_COLS = {"role", "heat_id", "filler_id", "remark"}
TESTPKG_COLS = {"pkg_no", "kind", "medium", "pressure", "test_date", "result", "reinstated", "remark"}
PUNCH_COLS = {"test_package_id", "category", "description", "status", "remark"}
MDR_COLS = {"doc_type", "title", "ref_no", "status", "file_path", "remark"}
PO_COLS = {"po_no", "vendor", "date", "status", "remark"}
MTO_COLS = {"drawing_id", "item_name", "spec", "material", "size", "schedule",
            "qty", "unit", "source", "status", "po_id", "remark"}


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
        "heats": db.query("SELECT id,heat_no,spec FROM material_heat WHERE project_id=? ORDER BY heat_no", (pid,)),
        "fillers": db.query("SELECT id,batch_no,aws_class FROM filler_material WHERE project_id=? ORDER BY batch_no", (pid,)),
        "test_packages": db.query("SELECT id,pkg_no FROM test_package WHERE project_id=? ORDER BY pkg_no", (pid,)),
        "purchase_orders": db.query("SELECT id,po_no,vendor FROM purchase_order WHERE project_id=? ORDER BY po_no", (pid,)),
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
                drawing_id: int = 0, billing: str = "", spool_id: int = 0,
                size: str = "", material: str = "", weld_type: str = "",
                shop_field: str = "", welder: int = 0, nde_result: str = "",
                date_from: str = "", date_to: str = "",
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
    if spool_id:
        where += " AND wj.spool_id=?"; params.append(spool_id)
    if size:
        where += " AND wj.size=?"; params.append(size)
    if material:
        where += " AND wj.material=?"; params.append(material)
    if weld_type:
        where += " AND wt.code=?"; params.append(weld_type)
    if shop_field:
        where += " AND wj.shop_field=?"; params.append(shop_field)
    if welder:
        where += " AND (wj.welder_root_id=? OR wj.welder_cap_id=?)"; params += [welder, welder]
    if nde_result == "未檢":
        where += " AND wj.nde_result IS NULL"
    elif nde_result:
        where += " AND wj.nde_result=?"; params.append(nde_result)
    if date_from:
        where += " AND wj.weld_date>=?"; params.append(date_from)
    if date_to:
        where += " AND wj.weld_date<=?"; params.append(date_to)
    base = (
        "FROM weld_joint wj "
        "LEFT JOIN drawing d ON wj.drawing_id=d.id "
        "LEFT JOIN pipe_line pl ON wj.line_id=pl.id "
        "LEFT JOIN system s ON pl.system_id=s.id "
        "LEFT JOIN weld_type wt ON wj.weld_type_id=wt.id "
        "LEFT JOIN billing_period bp ON wj.billing_period_id=bp.id "
        "LEFT JOIN spool sp ON wj.spool_id=sp.id "
        f"{where}")
    rows = db.query(
        "SELECT wj.id, wj.joint_no, wj.size, wj.thickness, wj.material, "
        "wj.shop_field, wj.weld_date, wj.status, wj.nde_type, wj.nde_result, "
        "wj.db_count, wj.claim_status, wj.remark, "
        "d.drawing_no, d.serial_no, s.code AS system_code, wt.code AS weld_type, "
        "bp.code AS billing_period, sp.spool_no "
        + base + " ORDER BY d.serial_no, wj.joint_no LIMIT ? OFFSET ?",
        params + [limit, offset])
    total = db.query_one("SELECT COUNT(*) c " + base, params)["c"]
    return {"rows": rows, "total": total}


@app.get("/api/projects/{pid}/filter-options")
def filter_options(pid: int):
    def g(sql):
        return db.query(sql, (pid,))
    return {
        "size": g("SELECT size AS v, COUNT(*) n FROM weld_joint WHERE project_id=? AND size IS NOT NULL AND size<>'' GROUP BY size ORDER BY n DESC"),
        "material": g("SELECT material AS v, COUNT(*) n FROM weld_joint WHERE project_id=? AND material IS NOT NULL AND material<>'' GROUP BY material ORDER BY n DESC"),
        "weld_type": g("SELECT wt.code AS v, COUNT(*) n FROM weld_joint wj JOIN weld_type wt ON wj.weld_type_id=wt.id WHERE wj.project_id=? GROUP BY wt.code ORDER BY n DESC"),
        "shop_field": g("SELECT shop_field AS v, COUNT(*) n FROM weld_joint WHERE project_id=? AND shop_field IS NOT NULL AND shop_field<>'' GROUP BY shop_field ORDER BY n DESC"),
        "nde_result": g("SELECT COALESCE(nde_result,'未檢') AS v, COUNT(*) n FROM weld_joint WHERE project_id=? GROUP BY COALESCE(nde_result,'未檢') ORDER BY n DESC"),
        "status": g("SELECT status AS v, COUNT(*) n FROM weld_joint WHERE project_id=? GROUP BY status ORDER BY n DESC"),
    }


@app.get("/api/joints/{jid}")
def get_joint(jid: int):
    j = db.query_one("SELECT * FROM weld_joint WHERE id=?", (jid,))
    if not j:
        raise HTTPException(404, "找不到焊口")
    j["inspections"] = db.query("SELECT * FROM inspection WHERE weld_joint_id=? ORDER BY id", (jid,))
    j["materials"] = db.query(
        "SELECT jm.*, mh.heat_no, fm.batch_no, fm.aws_class FROM joint_material jm "
        "LEFT JOIN material_heat mh ON jm.heat_id=mh.id "
        "LEFT JOIN filler_material fm ON jm.filler_id=fm.id "
        "WHERE jm.weld_joint_id=? ORDER BY jm.id", (jid,))
    return j


@app.post("/api/projects/{pid}/joints")
def create_joint(pid: int, payload: dict = Body(...)):
    data = pick(payload, JOINT_COLS)
    data["project_id"] = pid
    if not data.get("joint_no"):
        raise HTTPException(400, "需要銲口編號")
    data.setdefault("status", "規劃")
    if data.get("db_count") in (None, "") and data.get("size"):
        data["db_count"] = sizes.db_count(data.get("size"), data.get("db_factor") or 1)
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
    if data.get("db_count") in (None, "") and data.get("size"):
        data["db_count"] = sizes.db_count(data.get("size"), data.get("db_factor") or 1)
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


@app.post("/api/joints/batch")
def batch_update_joints(payload: dict = Body(...)):
    """批次更新多個焊口的單一欄位(白名單)。payload: {ids:[...], field, value}"""
    ids = payload.get("ids") or []
    field = payload.get("field")
    value = payload.get("value")
    allowed = {"weld_date", "welder_root_id", "welder_cap_id", "status",
               "billing_period_id", "shop_field", "claim_status", "nde_result",
               "subcontractor", "test_package_id", "spool_id"}
    if field not in allowed:
        raise HTTPException(400, "不允許的批次欄位")
    if value in ("", None):
        value = None
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for jid in ids:
        db.execute(f"UPDATE weld_joint SET {field}=?, updated_at=? WHERE id=?", (value, ts, jid)); n += 1
    db.log(op(payload), "UPDATE", "weld_joint", 0, f"批次更新 {field} 共 {n} 筆")
    return {"updated": n}


@app.post("/api/projects/{pid}/joints/recompute-db")
def recompute_db(pid: int, payload: dict = Body(default={})):
    """為 DB數 空白(預設)且有尺寸的焊口,自動補算 max(1,吋)×係數。"""
    only_blank = (payload or {}).get("only_blank", True)
    where = "project_id=? AND size IS NOT NULL"
    if only_blank:
        where += " AND db_count IS NULL"
    rows = db.query(f"SELECT id, size, db_factor FROM weld_joint WHERE {where}", (pid,))
    n = 0
    for r in rows:
        v = sizes.db_count(r["size"], r["db_factor"] or 1)
        if v is not None:
            db.execute("UPDATE weld_joint SET db_count=? WHERE id=?", (v, r["id"])); n += 1
    db.log(op(payload), "UPDATE", "weld_joint", pid, f"重算 DB數 {n} 筆")
    return {"updated": n}


# ============================================================
#  Spool 預製分段
# ============================================================
@app.get("/api/projects/{pid}/spools")
def list_spools(pid: int, q: str = "", drawing_id: int = 0):
    where = "WHERE sp.project_id=?"
    params = [pid]
    if drawing_id:
        where += " AND sp.drawing_id=?"; params.append(drawing_id)
    if q:
        where += " AND (sp.spool_no LIKE ? OR d.drawing_no LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    rows = db.query(
        "SELECT sp.*, d.drawing_no, d.serial_no, "
        "(SELECT COUNT(*) FROM weld_joint w WHERE w.spool_id=sp.id) AS joint_count, "
        "(SELECT COUNT(*) FROM weld_joint w WHERE w.spool_id=sp.id AND w.weld_date IS NOT NULL) AS welded, "
        "(SELECT COALESCE(SUM(db_count),0) FROM weld_joint w WHERE w.spool_id=sp.id) AS db "
        "FROM spool sp LEFT JOIN drawing d ON sp.drawing_id=d.id "
        f"{where} ORDER BY d.serial_no, sp.spool_no", params)
    return {"rows": rows, "total": len(rows)}


@app.get("/api/drawings/{did}/spools")
def list_drawing_spools(did: int):
    return db.query("SELECT id, spool_no, shop_field, status FROM spool "
                    "WHERE drawing_id=? ORDER BY spool_no", (did,))


@app.post("/api/projects/{pid}/spools")
def create_spool(pid: int, payload: dict = Body(...)):
    data = pick(payload, SPOOL_COLS); data["project_id"] = pid
    if not data.get("spool_no"):
        raise HTTPException(400, "需要 spool 編號")
    try:
        sid = db.insert("spool", data, op(payload), f"新增 spool {data['spool_no']}")
    except Exception as e:
        raise HTTPException(409, f"spool 重複或錯誤:{e}")
    return db.query_one("SELECT * FROM spool WHERE id=?", (sid,))


@app.put("/api/spools/{sid}")
def update_spool(sid: int, payload: dict = Body(...)):
    db.update("spool", sid, pick(payload, SPOOL_COLS), op(payload), f"更新 spool #{sid}")
    return db.query_one("SELECT * FROM spool WHERE id=?", (sid,))


@app.delete("/api/spools/{sid}")
def delete_spool(sid: int, operator: str = "user"):
    db.execute("UPDATE weld_joint SET spool_id=NULL WHERE spool_id=?", (sid,))
    db.delete("spool", sid, operator)
    return {"ok": True}


@app.post("/api/spools/{sid}/assign")
def assign_joints_to_spool(sid: int, payload: dict = Body(...)):
    """把一批焊口指派到此 spool。payload: {joint_ids:[...]}"""
    ids = payload.get("joint_ids") or []
    n = 0
    for jid in ids:
        db.execute("UPDATE weld_joint SET spool_id=? WHERE id=?", (sid, jid)); n += 1
    db.log(op(payload), "UPDATE", "spool", sid, f"指派 {n} 個焊口到 spool #{sid}")
    return {"assigned": n}


@app.post("/api/projects/{pid}/spools/auto-build")
def auto_build_spools(pid: int, payload: dict = Body(default={})):
    """為每張圖的預製(S)且尚未歸 spool 的焊口,各建一個預設 spool 並掛上。"""
    operator = op(payload)
    dwgs = db.query(
        "SELECT DISTINCT d.id, d.serial_no, d.drawing_no FROM drawing d "
        "JOIN weld_joint w ON w.drawing_id=d.id "
        "WHERE d.project_id=? AND w.shop_field='S' AND w.spool_id IS NULL", (pid,))
    built = 0
    for d in dwgs:
        base = d["serial_no"] or d["drawing_no"] or str(d["id"])
        spool_no = f"{base}-S01"
        existing = db.query_one(
            "SELECT id FROM spool WHERE project_id=? AND drawing_id=? AND spool_no=?",
            (pid, d["id"], spool_no))
        if existing:
            sid = existing["id"]
        else:
            sid = db.execute(
                "INSERT INTO spool (project_id,drawing_id,spool_no,shop_field,status) "
                "VALUES (?,?,?,?,?)", (pid, d["id"], spool_no, "S", "規劃"))
            built += 1
        db.execute("UPDATE weld_joint SET spool_id=? "
                   "WHERE drawing_id=? AND shop_field='S' AND spool_id IS NULL", (sid, d["id"]))
    assigned = db.query_one(
        "SELECT COUNT(*) c FROM weld_joint WHERE project_id=? AND spool_id IS NOT NULL", (pid,))["c"]
    db.log(operator, "UPDATE", "spool", pid, f"自動建立 spool {built} 個")
    return {"built": built, "assigned_total": assigned}


# ============================================================
#  材料追溯:爐號/MTR、銲材、焊口材料
# ============================================================
@app.get("/api/projects/{pid}/heats")
def list_heats(pid: int):
    return db.query("SELECT * FROM material_heat WHERE project_id=? ORDER BY heat_no", (pid,))


@app.post("/api/projects/{pid}/heats")
def create_heat(pid: int, payload: dict = Body(...)):
    data = pick(payload, HEAT_COLS); data["project_id"] = pid
    if not data.get("heat_no"):
        raise HTTPException(400, "需要爐號")
    try:
        hid = db.insert("material_heat", data, op(payload), f"新增爐號 {data['heat_no']}")
    except Exception as e:
        raise HTTPException(409, f"爐號重複或錯誤:{e}")
    return db.query_one("SELECT * FROM material_heat WHERE id=?", (hid,))


@app.put("/api/heats/{hid}")
def update_heat(hid: int, payload: dict = Body(...)):
    db.update("material_heat", hid, pick(payload, HEAT_COLS), op(payload))
    return db.query_one("SELECT * FROM material_heat WHERE id=?", (hid,))


@app.delete("/api/heats/{hid}")
def delete_heat(hid: int, operator: str = "user"):
    db.delete("material_heat", hid, operator)
    return {"ok": True}


@app.get("/api/projects/{pid}/fillers")
def list_fillers(pid: int):
    return db.query("SELECT * FROM filler_material WHERE project_id=? ORDER BY batch_no", (pid,))


@app.post("/api/projects/{pid}/fillers")
def create_filler(pid: int, payload: dict = Body(...)):
    data = pick(payload, FILLER_COLS); data["project_id"] = pid
    if not data.get("batch_no"):
        raise HTTPException(400, "需要批號")
    try:
        fid = db.insert("filler_material", data, op(payload), f"新增銲材 {data['batch_no']}")
    except Exception as e:
        raise HTTPException(409, f"批號重複或錯誤:{e}")
    return db.query_one("SELECT * FROM filler_material WHERE id=?", (fid,))


@app.put("/api/fillers/{fid}")
def update_filler(fid: int, payload: dict = Body(...)):
    db.update("filler_material", fid, pick(payload, FILLER_COLS), op(payload))
    return db.query_one("SELECT * FROM filler_material WHERE id=?", (fid,))


@app.delete("/api/fillers/{fid}")
def delete_filler(fid: int, operator: str = "user"):
    db.delete("filler_material", fid, operator)
    return {"ok": True}


@app.post("/api/joints/{jid}/materials")
def add_joint_material(jid: int, payload: dict = Body(...)):
    data = pick(payload, JMAT_COLS); data["weld_joint_id"] = jid
    cols = ", ".join(data.keys()); ph = ", ".join("?" for _ in data)
    mid = db.execute(f"INSERT INTO joint_material ({cols}) VALUES ({ph})", tuple(data.values()))
    db.log(op(payload), "CREATE", "joint_material", mid, f"焊口 #{jid} 掛材料")
    return db.query_one("SELECT * FROM joint_material WHERE id=?", (mid,))


@app.delete("/api/jmaterials/{mid}")
def delete_joint_material(mid: int, operator: str = "user"):
    db.delete("joint_material", mid, operator)
    return {"ok": True}


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
#  試壓包 / Punch
# ============================================================
@app.get("/api/projects/{pid}/test-packages")
def list_test_packages(pid: int):
    return db.query(
        "SELECT tp.*, "
        "(SELECT COUNT(*) FROM weld_joint w WHERE w.test_package_id=tp.id) joints, "
        "(SELECT COUNT(*) FROM punch_item p WHERE p.test_package_id=tp.id AND p.status!='已結') punch_open "
        "FROM test_package tp WHERE project_id=? ORDER BY pkg_no", (pid,))


@app.post("/api/projects/{pid}/test-packages")
def create_test_package(pid: int, payload: dict = Body(...)):
    data = pick(payload, TESTPKG_COLS); data["project_id"] = pid
    if not data.get("pkg_no"):
        raise HTTPException(400, "需要試壓包編號")
    try:
        tid = db.insert("test_package", data, op(payload), f"新增試壓包 {data['pkg_no']}")
    except Exception as e:
        raise HTTPException(409, f"試壓包重複或錯誤:{e}")
    return db.query_one("SELECT * FROM test_package WHERE id=?", (tid,))


@app.put("/api/test-packages/{tid}")
def update_test_package(tid: int, payload: dict = Body(...)):
    db.update("test_package", tid, pick(payload, TESTPKG_COLS), op(payload))
    return db.query_one("SELECT * FROM test_package WHERE id=?", (tid,))


@app.delete("/api/test-packages/{tid}")
def delete_test_package(tid: int, operator: str = "user"):
    db.execute("UPDATE weld_joint SET test_package_id=NULL WHERE test_package_id=?", (tid,))
    db.delete("test_package", tid, operator)
    return {"ok": True}


@app.post("/api/test-packages/{tid}/assign")
def assign_joints_to_pkg(tid: int, payload: dict = Body(...)):
    ids = payload.get("joint_ids") or []
    n = 0
    for jid in ids:
        db.execute("UPDATE weld_joint SET test_package_id=? WHERE id=?", (tid, jid)); n += 1
    db.log(op(payload), "UPDATE", "test_package", tid, f"指派 {n} 個焊口到試壓包 #{tid}")
    return {"assigned": n}


@app.get("/api/test-packages/{tid}/punch")
def list_punch(tid: int):
    return db.query("SELECT * FROM punch_item WHERE test_package_id=? ORDER BY id", (tid,))


@app.post("/api/test-packages/{tid}/punch")
def create_punch(tid: int, payload: dict = Body(...)):
    data = pick(payload, PUNCH_COLS); data["test_package_id"] = tid
    tp = db.query_one("SELECT project_id FROM test_package WHERE id=?", (tid,))
    data["project_id"] = tp["project_id"] if tp else None
    cols = ", ".join(data.keys()); ph = ", ".join("?" for _ in data)
    pn = db.execute(f"INSERT INTO punch_item ({cols}) VALUES ({ph})", tuple(data.values()))
    db.log(op(payload), "CREATE", "punch_item", pn, "新增 punch")
    return db.query_one("SELECT * FROM punch_item WHERE id=?", (pn,))


@app.put("/api/punch/{punch_id}")
def update_punch(punch_id: int, payload: dict = Body(...)):
    db.update("punch_item", punch_id, pick(payload, PUNCH_COLS), op(payload))
    return db.query_one("SELECT * FROM punch_item WHERE id=?", (punch_id,))


@app.delete("/api/punch/{punch_id}")
def delete_punch(punch_id: int, operator: str = "user"):
    db.delete("punch_item", punch_id, operator)
    return {"ok": True}


# ============================================================
#  品保卷冊 MDR
# ============================================================
@app.get("/api/projects/{pid}/mdr")
def list_mdr(pid: int):
    return db.query("SELECT * FROM mdr_document WHERE project_id=? ORDER BY id DESC", (pid,))


@app.post("/api/projects/{pid}/mdr")
def create_mdr(pid: int, payload: dict = Body(...)):
    data = pick(payload, MDR_COLS); data["project_id"] = pid
    mid = db.insert("mdr_document", data, op(payload), f"新增卷冊 {data.get('title') or ''}")
    return db.query_one("SELECT * FROM mdr_document WHERE id=?", (mid,))


@app.put("/api/mdr/{mid}")
def update_mdr(mid: int, payload: dict = Body(...)):
    db.update("mdr_document", mid, pick(payload, MDR_COLS), op(payload))
    return db.query_one("SELECT * FROM mdr_document WHERE id=?", (mid,))


@app.delete("/api/mdr/{mid}")
def delete_mdr(mid: int, operator: str = "user"):
    db.delete("mdr_document", mid, operator)
    return {"ok": True}


# ============================================================
#  採購 / MTO 物料
# ============================================================
@app.get("/api/projects/{pid}/purchase-orders")
def list_pos(pid: int):
    return db.query(
        "SELECT po.*, (SELECT COUNT(*) FROM mto_item m WHERE m.po_id=po.id) items "
        "FROM purchase_order po WHERE project_id=? ORDER BY po_no", (pid,))


@app.post("/api/projects/{pid}/purchase-orders")
def create_po(pid: int, payload: dict = Body(...)):
    data = pick(payload, PO_COLS); data["project_id"] = pid
    if not data.get("po_no"):
        raise HTTPException(400, "需要採購單號")
    try:
        poid = db.insert("purchase_order", data, op(payload), f"新增採購單 {data['po_no']}")
    except Exception as e:
        raise HTTPException(409, f"採購單重複或錯誤:{e}")
    return db.query_one("SELECT * FROM purchase_order WHERE id=?", (poid,))


@app.put("/api/purchase-orders/{poid}")
def update_po(poid: int, payload: dict = Body(...)):
    db.update("purchase_order", poid, pick(payload, PO_COLS), op(payload))
    return db.query_one("SELECT * FROM purchase_order WHERE id=?", (poid,))


@app.delete("/api/purchase-orders/{poid}")
def delete_po(poid: int, operator: str = "user"):
    db.execute("UPDATE mto_item SET po_id=NULL WHERE po_id=?", (poid,))
    db.delete("purchase_order", poid, operator)
    return {"ok": True}


@app.get("/api/projects/{pid}/mto")
def list_mto(pid: int, status: str = "", q: str = ""):
    where = "WHERE m.project_id=?"; params = [pid]
    if status:
        where += " AND m.status=?"; params.append(status)
    if q:
        where += " AND (m.item_name LIKE ? OR m.spec LIKE ? OR m.material LIKE ?)"; params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    return db.query(
        "SELECT m.*, d.drawing_no, po.po_no FROM mto_item m "
        "LEFT JOIN drawing d ON m.drawing_id=d.id "
        "LEFT JOIN purchase_order po ON m.po_id=po.id "
        f"{where} ORDER BY m.status, m.id DESC", params)


@app.post("/api/projects/{pid}/mto")
def create_mto(pid: int, payload: dict = Body(...)):
    data = pick(payload, MTO_COLS); data["project_id"] = pid
    mid = db.insert("mto_item", data, op(payload), f"新增物料 {data.get('item_name') or ''}")
    return db.query_one("SELECT * FROM mto_item WHERE id=?", (mid,))


@app.put("/api/mto/{mid}")
def update_mto(mid: int, payload: dict = Body(...)):
    db.update("mto_item", mid, pick(payload, MTO_COLS), op(payload))
    return db.query_one("SELECT * FROM mto_item WHERE id=?", (mid,))


@app.delete("/api/mto/{mid}")
def delete_mto(mid: int, operator: str = "user"):
    db.delete("mto_item", mid, operator)
    return {"ok": True}


# ============================================================
#  匯入 / 匯出 Excel
# ============================================================
@app.post("/api/import")
async def import_excel(file: UploadFile = File(...), code: str = Form(...),
                       name: str = Form(...), owner: str = Form(""),
                       operator: str = Form("user"), mode: str = Form("merge")):
    suffix = os.path.splitext(file.filename)[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read()); tmp.close()
        summary = importer.import_weld_control(tmp.name, code, name, owner or None, operator, mode)
    except Exception as e:
        raise HTTPException(400, f"匯入失敗:{e}")
    finally:
        os.unlink(tmp.name)
    return summary


@app.post("/api/projects/{pid}/merge-completion")
async def merge_completion_api(pid: int, file: UploadFile = File(...), operator: str = Form("user")):
    suffix = os.path.splitext(file.filename)[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read()); tmp.close()
        result = importer.merge_completion_file(tmp.name, pid, operator)
    except Exception as e:
        raise HTTPException(400, f"合併失敗:{e}")
    finally:
        os.unlink(tmp.name)
    return result


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
