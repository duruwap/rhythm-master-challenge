"""DB 연결·DDL 적용 헬퍼 (서버와 배치가 함께 사용)."""

from __future__ import annotations

import glob
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DDL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddl")


def default_db_path() -> str:
    return os.environ.get("RMC_DATABASE", os.path.join(BASE_DIR, "instance", "rhythm_master.sqlite3"))


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or default_db_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def apply_ddl(conn: sqlite3.Connection) -> None:
    """db/ddl/*.sql 을 파일명 순서대로 적용 (모두 IF NOT EXISTS 라 반복 실행해도 안전)."""
    for path in sorted(glob.glob(os.path.join(DDL_DIR, "*.sql"))):
        with open(path, encoding="utf-8") as f:
            conn.executescript(f.read())
    conn.commit()
