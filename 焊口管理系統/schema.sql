-- ============================================================
--  焊口管理系統 (Weld Joint Management System)
--  企業級 SQLite Schema
--  層級:專案 → 系統 → 管線 → 圖面(ISO) → 焊口
--  旁支:圖面版次 / 焊工 / WPS / 檢驗(NDE) / 請款 / 問題 / 接頭 / 稽核
-- ============================================================
PRAGMA foreign_keys = ON;

-- ---------- 專案 ----------
CREATE TABLE IF NOT EXISTS project (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT UNIQUE NOT NULL,          -- 專案代號 e.g. cp-129
  name        TEXT NOT NULL,                 -- 專案名稱
  owner       TEXT,                          -- 業主
  contractor  TEXT,                          -- 承攬商(本公司)
  description TEXT,
  status      TEXT DEFAULT '進行中',          -- 進行中/結案
  created_at  TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- 系統 (System) ----------
CREATE TABLE IF NOT EXISTS system (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  code        TEXT NOT NULL,                 -- 系統代碼 AI/AP/FF
  name_zh     TEXT,                          -- 系統中文名
  pipe_class  TEXT,                          -- 管道等級 class
  material    TEXT,                          -- 材質
  color       TEXT,                          -- 3D 顏色分類
  UNIQUE(project_id, code)
);

-- ---------- 銲接型式 (Weld Type) ----------
CREATE TABLE IF NOT EXISTS weld_type (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  code        TEXT NOT NULL,                 -- BW/SW/IW/NPT/RF/FW
  name        TEXT,                          -- 對焊/插承焊...
  factor      REAL DEFAULT 1,               -- 係數(計 DB 數用)
  UNIQUE(project_id, code)
);

-- ---------- WPS 銲接程序規範 ----------
CREATE TABLE IF NOT EXISTS wps (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id     INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  wps_no         TEXT NOT NULL,
  process        TEXT,                       -- GTAW/SMAW/FCAW/SAW
  material_group TEXT,                       -- P-No / Group
  thk_min        REAL,
  thk_max        REAL,
  remark         TEXT,
  UNIQUE(project_id, wps_no)
);

-- ---------- 焊工 (Welder) ----------
CREATE TABLE IF NOT EXISTS welder (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  stamp       TEXT NOT NULL,                 -- 鋼印代號
  name        TEXT,
  cert_no     TEXT,                          -- 證照號
  cert_expiry TEXT,                          -- 證照到期
  process     TEXT,                          -- 合格製程
  active      INTEGER DEFAULT 1,
  UNIQUE(project_id, stamp)
);

-- ---------- 管線 (Line) ----------
CREATE TABLE IF NOT EXISTS pipe_line (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  line_no      TEXT NOT NULL,                -- LINE NO.
  system_id    INTEGER REFERENCES system(id),
  size         TEXT,
  pipe_class   TEXT,
  material     TEXT,
  medium       TEXT,                         -- 介質
  od           TEXT,                          -- 外徑×壁厚
  thickness    TEXT,
  design_temp  TEXT,
  design_press TEXT,
  oper_temp    TEXT,
  oper_press   TEXT,
  insulation   TEXT,                          -- 絕熱/保溫
  nde_req      TEXT,                          -- 焊縫檢測要求
  test_req     TEXT,                          -- 試壓要求
  pid_no       TEXT,                          -- P&ID 圖號
  remark       TEXT,
  UNIQUE(project_id, line_no)
);

-- ---------- 圖面 (Drawing / ISO) ----------
CREATE TABLE IF NOT EXISTS drawing (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  drawing_no   TEXT NOT NULL,                -- 圖號 (業主提供)
  serial_no    TEXT,                         -- 流水號 (公司唯一值,對圖檔)
  line_id      INTEGER REFERENCES pipe_line(id),
  system_id    INTEGER REFERENCES system(id),
  size         TEXT,
  pipe_class   TEXT,
  sheet_index  INTEGER,                      -- 第幾張
  num_sheets   INTEGER,                      -- 共幾張
  current_rev  TEXT,                         -- 現行版次
  rev_date     TEXT,
  scan_date    TEXT,                         -- 預製圖掃描日期
  status       TEXT DEFAULT '啟用',           -- 啟用/作廢
  pdf_path     TEXT,                         -- PDF 路徑/連結
  remark       TEXT,
  created_at   TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(project_id, drawing_no)
);

-- ---------- 圖面版次 (Drawing Revision) ----------
CREATE TABLE IF NOT EXISTS drawing_revision (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  drawing_id INTEGER NOT NULL REFERENCES drawing(id) ON DELETE CASCADE,
  rev_code   TEXT NOT NULL,                  -- REV.A / 0 / 1 / 2
  rev_date   TEXT,
  note       TEXT
);

-- ---------- 請款期別 (Billing Period) ----------
CREATE TABLE IF NOT EXISTS billing_period (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  code       TEXT NOT NULL,                  -- 2026.03
  date_from  TEXT,
  date_to    TEXT,
  unit_price REAL,                           -- 單口單價(可選)
  status     TEXT DEFAULT '未請款',           -- 未請款/已送審/已請款
  note       TEXT,
  UNIQUE(project_id, code)
);

-- ---------- Spool 預製分段 ----------
-- 圖面 → spool → 焊口。廠內預製的最小單位;焊口可歸屬某個 spool。
CREATE TABLE IF NOT EXISTS spool (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  drawing_id  INTEGER REFERENCES drawing(id) ON DELETE CASCADE,
  spool_no    TEXT NOT NULL,
  shop_field  TEXT DEFAULT 'S',
  status      TEXT DEFAULT '規劃',
  fab_dwg_no  TEXT,
  scan_date   TEXT,
  ship_date   TEXT,
  remark      TEXT,
  created_at  TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(project_id, drawing_id, spool_no)
);

-- ---------- 材料追溯:母材爐號 / MTR ----------
CREATE TABLE IF NOT EXISTS material_heat (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  heat_no     TEXT NOT NULL,                 -- 爐號
  spec        TEXT,                          -- 材質規格
  p_no        TEXT,                          -- P-No
  size        TEXT,
  schedule    TEXT,
  mtr_no      TEXT,                          -- MTR 證明文件號
  mtr_path    TEXT,                          -- MTR 路徑/連結
  pmi_done    INTEGER DEFAULT 0,
  remark      TEXT,
  created_at  TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(project_id, heat_no)
);

-- ---------- 材料追溯:銲材(消耗品) ----------
CREATE TABLE IF NOT EXISTS filler_material (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_no    TEXT NOT NULL,                 -- 批號
  aws_class   TEXT,                          -- AWS class
  f_no        TEXT,                          -- F-No
  spec        TEXT,
  bake_log    TEXT,                          -- 烘箱紀錄
  remark      TEXT,
  created_at  TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(project_id, batch_no)
);

-- ---------- 焊口 ↔ 材料(多值,含側別) ----------
CREATE TABLE IF NOT EXISTS joint_material (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  weld_joint_id INTEGER NOT NULL REFERENCES weld_joint(id) ON DELETE CASCADE,
  role          TEXT,                        -- A側母材/B側母材/銲材/背檔氣
  heat_id       INTEGER REFERENCES material_heat(id) ON DELETE SET NULL,
  filler_id     INTEGER REFERENCES filler_material(id) ON DELETE SET NULL,
  remark        TEXT
);

-- ---------- 焊口 (Weld Joint) ★核心★ ----------
CREATE TABLE IF NOT EXISTS weld_joint (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id     INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  drawing_id     INTEGER REFERENCES drawing(id) ON DELETE SET NULL,
  line_id        INTEGER REFERENCES pipe_line(id),
  spool_id       INTEGER REFERENCES spool(id) ON DELETE SET NULL,  -- 所屬 spool
  joint_no       TEXT NOT NULL,              -- 銲口編號
  -- 規格
  size           TEXT,
  thickness      TEXT,
  schedule       TEXT,                       -- SCH
  material       TEXT,
  weld_type_id   INTEGER REFERENCES weld_type(id),
  joint_category TEXT,                       -- 分類(消防/工業級/區域)
  db_factor      REAL DEFAULT 1,            -- 係數
  db_count       REAL,                       -- DB 數(計量)
  shop_field     TEXT,                       -- S 預製 / F 現場
  -- 製程與追溯
  welding_process TEXT,                      -- GTAW/SMAW...
  wps_id         INTEGER REFERENCES wps(id),
  welder_root_id INTEGER REFERENCES welder(id),  -- 打底焊工
  welder_cap_id  INTEGER REFERENCES welder(id),  -- 填充/蓋面焊工
  fitup_by       TEXT,                       -- 組對者
  fitup_date     TEXT,                       -- 組對日期
  weld_date      TEXT,                       -- 配管(完銲)完成日期
  heat_no        TEXT,                       -- 爐號(材料追溯)
  -- NDE 摘要(明細見 inspection)
  nde_type       TEXT,                       -- RT/PT/MT/UT/VT
  nde_percent    TEXT,                       -- 比例 10%/100%
  nde_date       TEXT,
  nde_result     TEXT,                       -- 合格/不合格/未檢
  nde_report_no  TEXT,
  repair_count   INTEGER DEFAULT 0,         -- 補焊次數
  -- PWHT 後熱處理
  pwht_required  INTEGER DEFAULT 0,
  pwht_done      INTEGER DEFAULT 0,
  pwht_date      TEXT,
  -- 試壓
  test_package   TEXT,                       -- 試壓包
  test_date      TEXT,
  test_result    TEXT,
  -- 狀態與商務
  status         TEXT DEFAULT '規劃',         -- 規劃/組對/完銲/待檢/合格/不合格/試壓/完成
  subcontractor  TEXT,                       -- 承包商(外包)
  billing_period_id INTEGER REFERENCES billing_period(id),
  claim_status   TEXT DEFAULT '未請款',        -- 未請款/已請款
  remark         TEXT,
  created_at     TEXT DEFAULT (datetime('now','localtime')),
  updated_at     TEXT
);

-- ---------- 檢驗事件 (Inspection / NDE log) ----------
CREATE TABLE IF NOT EXISTS inspection (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  weld_joint_id INTEGER NOT NULL REFERENCES weld_joint(id) ON DELETE CASCADE,
  method        TEXT,                        -- RT/PT/MT/UT/VT
  percent       TEXT,
  request_date  TEXT,
  inspect_date  TEXT,
  result        TEXT,                        -- 合格/不合格
  report_no     TEXT,
  rt_drawing_no TEXT,
  inspector     TEXT,
  remark        TEXT
);

-- ---------- 問題焊口 / 議題 (Issue) ----------
CREATE TABLE IF NOT EXISTS joint_issue (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  weld_joint_id INTEGER REFERENCES weld_joint(id) ON DELETE CASCADE,
  drawing_id    INTEGER REFERENCES drawing(id) ON DELETE CASCADE,
  issue_type    TEXT,                        -- 欠接頭/新增焊口/圖面問題/缺漏
  description   TEXT,
  status        TEXT DEFAULT '待處理',         -- 待處理/已處理
  created_at    TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- 接頭需求 (Fitting Requirement) ----------
CREATE TABLE IF NOT EXISTS fitting_requirement (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  weld_joint_id INTEGER REFERENCES weld_joint(id) ON DELETE CASCADE,
  drawing_id    INTEGER REFERENCES drawing(id),
  qty           REAL,
  size          TEXT,
  material      TEXT,
  remark        TEXT
);

-- ---------- 稽核日誌 (Audit Log) ----------
CREATE TABLE IF NOT EXISTS audit_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT DEFAULT (datetime('now','localtime')),
  operator  TEXT,                            -- 操作人
  action    TEXT,                            -- CREATE/UPDATE/DELETE/IMPORT
  entity    TEXT,                            -- 資料表
  entity_id INTEGER,
  summary   TEXT                             -- 可讀說明
);

-- ---------- 試壓包 (Test Package) ----------
CREATE TABLE IF NOT EXISTS test_package (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  pkg_no      TEXT NOT NULL,
  kind        TEXT,                          -- 水壓/氣壓
  medium      TEXT,
  pressure    TEXT,
  test_date   TEXT,
  result      TEXT,                          -- 合格/不合格
  reinstated  INTEGER DEFAULT 0,
  remark      TEXT,
  created_at  TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(project_id, pkg_no)
);

-- ---------- Punch List ----------
CREATE TABLE IF NOT EXISTS punch_item (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id      INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  test_package_id INTEGER REFERENCES test_package(id) ON DELETE CASCADE,
  category        TEXT,
  description     TEXT,
  status          TEXT DEFAULT '待處理',
  remark          TEXT,
  created_at      TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- 品保卷冊 (MDR / Turnover) ----------
CREATE TABLE IF NOT EXISTS mdr_document (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  doc_type    TEXT,
  title       TEXT,
  ref_no      TEXT,
  status      TEXT DEFAULT '待彙整',
  file_path   TEXT,
  remark      TEXT,
  created_at  TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- 採購單 (Purchase Order) ----------
CREATE TABLE IF NOT EXISTS purchase_order (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  po_no       TEXT NOT NULL,
  vendor      TEXT,
  date        TEXT,
  status      TEXT DEFAULT '已採購',
  remark      TEXT,
  UNIQUE(project_id, po_no)
);

-- ---------- 物料需求 (MTO) ----------
CREATE TABLE IF NOT EXISTS mto_item (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  drawing_id  INTEGER REFERENCES drawing(id) ON DELETE SET NULL,
  item_name   TEXT,
  spec        TEXT,
  material    TEXT,
  size        TEXT,
  schedule    TEXT,
  qty         REAL,
  unit        TEXT,
  source      TEXT,                          -- 自購/業主供料
  status      TEXT DEFAULT '需求',            -- 需求/已採購/到料/缺料
  po_id       INTEGER REFERENCES purchase_order(id) ON DELETE SET NULL,
  remark      TEXT,
  created_at  TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- 索引 ----------
CREATE INDEX IF NOT EXISTS idx_joint_project ON weld_joint(project_id);
CREATE INDEX IF NOT EXISTS idx_joint_drawing ON weld_joint(drawing_id);
CREATE INDEX IF NOT EXISTS idx_joint_status  ON weld_joint(status);
CREATE INDEX IF NOT EXISTS idx_joint_billing ON weld_joint(billing_period_id);
CREATE INDEX IF NOT EXISTS idx_spool_drawing ON spool(drawing_id);
CREATE INDEX IF NOT EXISTS idx_jmat_joint ON joint_material(weld_joint_id);
CREATE INDEX IF NOT EXISTS idx_drawing_project ON drawing(project_id);
CREATE INDEX IF NOT EXISTS idx_inspection_joint ON inspection(weld_joint_id);
CREATE INDEX IF NOT EXISTS idx_joint_size ON weld_joint(size);
CREATE INDEX IF NOT EXISTS idx_joint_material ON weld_joint(material);
CREATE INDEX IF NOT EXISTS idx_joint_shopfield ON weld_joint(shop_field);
CREATE INDEX IF NOT EXISTS idx_joint_welddate ON weld_joint(weld_date);
CREATE INDEX IF NOT EXISTS idx_joint_welderroot ON weld_joint(welder_root_id);
CREATE INDEX IF NOT EXISTS idx_punch_pkg ON punch_item(test_package_id);
CREATE INDEX IF NOT EXISTS idx_mto_drawing ON mto_item(drawing_id);
CREATE INDEX IF NOT EXISTS idx_mto_po ON mto_item(po_id);

-- ---------- 分析 View:焊口完整檢視 ----------
DROP VIEW IF EXISTS v_joint_full;
CREATE VIEW v_joint_full AS
SELECT
  wj.id, wj.project_id, wj.joint_no, wj.size, wj.thickness, wj.schedule,
  wj.material, wj.joint_category, wj.db_factor, wj.db_count, wj.shop_field,
  wj.weld_date, wj.status, wj.nde_type, wj.nde_result, wj.subcontractor,
  wj.claim_status, wj.remark,
  d.drawing_no, d.serial_no, d.current_rev,
  s.code  AS system_code, s.name_zh AS system_name,
  wt.code AS weld_type, wt.name AS weld_type_name,
  bp.code AS billing_period,
  wr.stamp AS welder_root, wc.stamp AS welder_cap
FROM weld_joint wj
LEFT JOIN drawing        d  ON wj.drawing_id = d.id
LEFT JOIN system         s  ON wj.line_id IS NOT NULL AND s.id = (SELECT system_id FROM pipe_line WHERE id = wj.line_id)
LEFT JOIN weld_type      wt ON wj.weld_type_id = wt.id
LEFT JOIN billing_period bp ON wj.billing_period_id = bp.id
LEFT JOIN welder         wr ON wj.welder_root_id = wr.id
LEFT JOIN welder         wc ON wj.welder_cap_id = wc.id;
