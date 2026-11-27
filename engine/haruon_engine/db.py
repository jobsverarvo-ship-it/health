"""SQLite 저장소. 파일 하나(data/haruon.db)에 모든 상태를 둔다."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import now_kst

SCHEMA = """
-- 공공데이터에서 가져온 원본 자료
CREATE TABLE IF NOT EXISTS raw_items (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    source_key  TEXT NOT NULL UNIQUE,     -- 같은 자료를 두 번 넣지 않기 위한 키
    category    TEXT NOT NULL,
    title       TEXT,
    payload     TEXT NOT NULL,            -- 원문 JSON
    source_name TEXT,
    source_url  TEXT,
    fetched_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',   -- new | drafted | skipped
    note        TEXT
);

-- 발송할 건강 정보 한 건
CREATE TABLE IF NOT EXISTS tips (
    id          INTEGER PRIMARY KEY,
    raw_id      INTEGER REFERENCES raw_items(id),
    dedupe_key  TEXT UNIQUE,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    action      TEXT NOT NULL DEFAULT '',
    caution     TEXT NOT NULL DEFAULT '',
    source_name TEXT,
    source_url  TEXT,
    tags        TEXT NOT NULL DEFAULT '[]',
    region      TEXT,                      -- 날씨·미세먼지처럼 지역이 정해진 정보
    valid_from  TEXT,                      -- 이 날짜부터 보낼 수 있음 (YYYY-MM-DD)
    valid_until TEXT,                      -- 이 날짜까지만 보냄
    priority    INTEGER NOT NULL DEFAULT 50,
    kind        TEXT NOT NULL DEFAULT 'evergreen',  -- evergreen | live
    writer      TEXT NOT NULL,             -- seed | ai | rule | template
    status      TEXT NOT NULL DEFAULT 'draft',      -- draft | approved | rejected
    flags       TEXT NOT NULL DEFAULT '[]',         -- 검토 때 볼 경고
    created_at  TEXT NOT NULL,
    reviewed_at TEXT,
    review_note TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    region    TEXT,
    interests TEXT NOT NULL DEFAULT '[]',
    plan      TEXT NOT NULL DEFAULT 'free',   -- free | member
    active    INTEGER NOT NULL DEFAULT 1
);

-- 누구에게 어떤 정보를 보냈는지 (같은 정보를 두 번 보내지 않기 위해)
CREATE TABLE IF NOT EXISTS sends (
    id        INTEGER PRIMARY KEY,
    user_id   TEXT NOT NULL,
    tip_id    INTEGER NOT NULL,
    send_date TEXT NOT NULL,
    channel   TEXT NOT NULL,
    UNIQUE (user_id, tip_id)
);

-- 날짜별 발송 계획
CREATE TABLE IF NOT EXISTS plans (
    user_id   TEXT NOT NULL,
    plan_date TEXT NOT NULL,
    tip_ids   TEXT NOT NULL,
    message   TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'planned',   -- planned | sent
    PRIMARY KEY (user_id, plan_date)
);

-- 페이지 위치 같은 작은 상태 값
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def stamp() -> str:
    return now_kst().isoformat(timespec="seconds")


def get_state(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def add_raw(conn: sqlite3.Connection, *, source: str, source_key: str, category: str,
            title: str, payload: dict, source_name: str, source_url: str | None = None) -> bool:
    """새 원본 자료를 넣는다. 이미 있으면 False."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO raw_items "
        "(source, source_key, category, title, payload, source_name, source_url, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source, source_key, category, title, json.dumps(payload, ensure_ascii=False),
         source_name, source_url, stamp()),
    )
    return cur.rowcount == 1


def add_tip(conn: sqlite3.Connection, **tip) -> int | None:
    """정보 한 건을 넣는다. dedupe_key 가 겹치면 넣지 않고 None."""
    tip.setdefault("tags", [])
    tip.setdefault("flags", [])
    tip["tags"] = json.dumps(tip["tags"], ensure_ascii=False)
    tip["flags"] = json.dumps(tip["flags"], ensure_ascii=False)
    tip.setdefault("created_at", stamp())
    cols = ", ".join(tip)
    marks = ", ".join("?" for _ in tip)
    cur = conn.execute(f"INSERT OR IGNORE INTO tips ({cols}) VALUES ({marks})", tuple(tip.values()))
    return cur.lastrowid if cur.rowcount == 1 else None


def tip_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["flags"] = json.loads(d.get("flags") or "[]")
    return d
