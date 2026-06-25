"""
db.py — SQLite 資料存取層
所有資料庫連線、初始化、查詢輔助與稽核日誌都集中在這裡。
不依賴 ORM,純 sqlite3,方便檢視與移植。
"""
import sqlite3
import os
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("WELD_DB", os.path.join(BASE_DIR, "weld.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """建立資料表(若不存在)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        sql = f.read()
    with get_conn() as conn:
        conn.executescript(sql)


# ---------- 查詢輔助 ----------
def query(sql, params=()):
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def query_one(sql, params=()):
    with get_conn() as conn:
        r = conn.execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


# ---------- 通用 insert / update ----------
def insert(table, data, operator=None, log_summary=None):
    cols = ", ".join(data.keys())
    ph = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({ph})"
    with get_conn() as conn:
        cur = conn.execute(sql, tuple(data.values()))
        new_id = cur.lastrowid
        _audit(conn, operator, "CREATE", table, new_id,
               log_summary or f"新增 {table} #{new_id}")
    return new_id


def update(table, row_id, data, operator=None, log_summary=None):
    if not data:
        return
    sets = ", ".join(f"{k}=?" for k in data)
    sql = f"UPDATE {table} SET {sets} WHERE id=?"
    with get_conn() as conn:
        conn.execute(sql, tuple(data.values()) + (row_id,))
        _audit(conn, operator, "UPDATE", table, row_id,
               log_summary or f"更新 {table} #{row_id}")


def delete(table, row_id, operator=None, log_summary=None):
    with get_conn() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
        _audit(conn, operator, "DELETE", table, row_id,
               log_summary or f"刪除 {table} #{row_id}")


# ---------- 稽核日誌 ----------
def _audit(conn, operator, action, entity, entity_id, summary):
    conn.execute(
        "INSERT INTO audit_log (operator, action, entity, entity_id, summary) "
        "VALUES (?,?,?,?,?)",
        (operator or "system", action, entity, entity_id, summary),
    )


def log(operator, action, entity, entity_id, summary):
    """供匯入等批次作業直接寫一筆稽核。"""
    with get_conn() as conn:
        _audit(conn, operator, action, entity, entity_id, summary)


# ---------- 預設參考資料 ----------
DEFAULT_WELD_TYPES = [
    ("BW", "對焊 Butt Weld", 1),
    ("SW", "插承焊 Socket Weld", 1),
    ("IW", "插入焊 Insert Weld", 1),
    ("FW", "角焊 Fillet Weld", 1),
    ("NPT", "螺紋 Threaded", 1),
    ("RF", "凸面法蘭 Raised Face", 1),
]


def seed_weld_types(project_id):
    for code, name, factor in DEFAULT_WELD_TYPES:
        try:
            execute(
                "INSERT OR IGNORE INTO weld_type (project_id, code, name, factor) "
                "VALUES (?,?,?,?)",
                (project_id, code, name, factor),
            )
        except Exception:
            pass


if __name__ == "__main__":
    init_db()
    print(f"資料庫已初始化:{DB_PATH}")
