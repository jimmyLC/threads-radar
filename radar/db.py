"""SQLite 存取層"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import TZ_OFFSET_HOURS, db_path, load_keywords

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def taipei_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)


@contextmanager
def connect():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, str(value)))


def init() -> None:
    """建表＋把 keywords.yaml 同步進 keywords 表（冪等）。"""
    with connect() as c:
        c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for term in load_keywords():
            c.execute("INSERT OR IGNORE INTO keywords(term) VALUES(?)", (term,))
        if get_setting(c, "mode") is None:
            set_setting(c, "mode", "dev")  # dev=未通過審查 / live=已通過
