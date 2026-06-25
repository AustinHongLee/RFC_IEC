"""
seed_template.py — 建立一個「示範範本」專案,把所有企業級欄位都填上,
方便你打開系統就看到完整能力(焊工、WPS、追溯、NDE、PWHT、試壓、請款)。
執行: python seed_template.py
"""
import db

CODE = "DEMO"


def run():
    db.init_db()
    ex = db.query_one("SELECT id FROM project WHERE code=?", (CODE,))
    if ex:
        db.delete("project", ex["id"], "seed", "重建示範專案")
    pid = db.insert("project", {
        "code": CODE, "name": "示範專案(範本)", "owner": "範例業主",
        "contractor": "勝一工程", "description": "展示焊口管理系統完整欄位的示範資料"},
        "seed", "建立示範專案")
    db.seed_weld_types(pid)

    # 系統
    sys_ids = {}
    for code, zh, cls, mat, color in [
        ("AI", "儀錶用空氣", "S11U", "304L", "淺綠"),
        ("FF", "泡沫消防", "S11U", "304L", "紅"),
        ("PW", "製程水", "AA1B", "C.S", "藍")]:
        sys_ids[code] = db.execute(
            "INSERT INTO system (project_id,code,name_zh,pipe_class,material,color) VALUES (?,?,?,?,?,?)",
            (pid, code, zh, cls, mat, color))

    # 焊工
    welders = {}
    for stamp, name, cert in [("W01", "陳志明", "ASME-IX-1001"),
                              ("W02", "林大山", "ASME-IX-1002"),
                              ("W03", "黃建宏", "ASME-IX-1003")]:
        welders[stamp] = db.execute(
            "INSERT INTO welder (project_id,stamp,name,cert_no,cert_expiry,process) VALUES (?,?,?,?,?,?)",
            (pid, stamp, name, cert, "2027-12-31", "GTAW/SMAW"))

    # WPS
    wps_id = db.execute(
        "INSERT INTO wps (project_id,wps_no,process,material_group,thk_min,thk_max,remark) VALUES (?,?,?,?,?,?,?)",
        (pid, "WPS-SS-01", "GTAW", "P-No.8", 1.0, 20.0, "不鏽鋼對焊"))

    wt = {w["code"]: w["id"] for w in db.query("SELECT id,code FROM weld_type WHERE project_id=?", (pid,))}

    # 管線 + 圖面 + 焊口
    lines = {}
    def line(no, sysc):
        if no not in lines:
            lines[no] = db.execute(
                "INSERT INTO pipe_line (project_id,line_no,system_id,size,material) VALUES (?,?,?,?,?)",
                (pid, no, sys_ids[sysc], "2\"", "304L"))
        return lines[no]

    samples = [
        # drawing_no, serial, sys, line, joints[(no,size,thk,mat,type,sf,date,status,nde,result)]
        ("1-S11U-AI-00001-001", "1", "AI", "AI-00001", [
            ("1", "2", "40S", "304L", "BW", "S", "2026-05-05", "完成", "RT", "合格"),
            ("2", "2", "40S", "304L", "BW", "S", "2026-05-05", "完成", "RT", "合格"),
            ("3", "1", "40S", "304L", "SW", "F", "2026-05-12", "合格", "PT", "合格"),
            ("4", "1", "40S", "304L", "SW", "F", None, "規劃", None, None)]),
        ("1-S11U-FF-00010-001", "2", "FF", "FF-00010", [
            ("1", "3", "10S", "304L", "BW", "S", "2026-06-01", "完成", "RT", "不合格"),
            ("2", "3", "10S", "304L", "BW", "S", "2026-06-01", "完成", "RT", "合格"),
            ("3", "3", "10S", "304L", "BW", "F", None, "組對", None, None)]),
        ("PW-0101-50-AA1B-001", "3", "PW", "PW-0101", [
            ("1", "2", "SCH40", "C.S", "BW", "S", "2026-06-10", "試壓", "RT", "合格"),
            ("2", "2", "SCH40", "C.S", "FW", "F", None, "規劃", None, None)]),
    ]
    for dno, serial, sysc, lno, joints in samples:
        lid = line(lno, sysc)
        did = db.execute(
            "INSERT INTO drawing (project_id,drawing_no,serial_no,line_id,system_id,size,pipe_class,"
            "num_sheets,current_rev,scan_date,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, dno, serial, lid, sys_ids[sysc], "2\"", "S11U", 1, "REV.1", "2026-04-20", "啟用"))
        for jno, size, thk, mat, typ, sf, date, status, nde, result in joints:
            jid = db.execute(
                "INSERT INTO weld_joint (project_id,drawing_id,line_id,joint_no,size,thickness,material,"
                "weld_type_id,db_factor,db_count,shop_field,welding_process,wps_id,welder_root_id,welder_cap_id,"
                "weld_date,heat_no,nde_type,nde_percent,nde_date,nde_result,pwht_required,status,claim_status,remark) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, did, lid, jno, size, thk, mat, wt.get(typ), 1, float(size),
                 sf, "GTAW", wps_id, welders["W01"], welders["W02"],
                 date, ("HT-" + date.replace("-", "")) if date else None,
                 nde, "10%" if nde else None, date if nde else None, result,
                 0, status, "未請款", ""))
            if nde:
                db.execute(
                    "INSERT INTO inspection (weld_joint_id,method,percent,inspect_date,result,report_no,inspector) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (jid, nde, "10%", date, result, "RPT-{:04d}".format(jid), "QC-王"))

    # 問題
    db.execute(
        "INSERT INTO joint_issue (project_id,drawing_id,issue_type,description,status) VALUES (?,?,?,?,?)",
        (pid, did, "欠接頭", "FF-00010 末端缺一個 3\" 彎頭,待業主確認", "待處理"))

    db.log("seed", "IMPORT", "project", pid, "建立示範範本資料")
    print(f"示範專案已建立 (project_id={pid})")


if __name__ == "__main__":
    run()
