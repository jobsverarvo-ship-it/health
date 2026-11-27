"""SQLite 데이터베이스 (파일 하나: server/data/app.db)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    phone       TEXT UNIQUE,          -- 휴대폰으로 가입한 분 (010-1234-5678)
    kakao_id    TEXT UNIQUE,          -- 카카오로 가입한 분
    interests   TEXT NOT NULL DEFAULT '[]',
    channel     TEXT NOT NULL DEFAULT 'kakao',   -- kakao | sms
    send_time   TEXT NOT NULL DEFAULT '8',       -- 7 | 8 | 9
    paused      INTEGER NOT NULL DEFAULT 0,
    plan        TEXT NOT NULL DEFAULT 'free',
    marketing   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 동의 기록 (언제 무엇에 동의했는지 남겨 둔다)
CREATE TABLE IF NOT EXISTS consents (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item        TEXT NOT NULL,
    agreed      INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

-- 로그인 상태. 쿠키에는 무작위 토큰을, 여기에는 그 해시만 저장한다.
-- user_id 가 비어 있으면 '본인 확인은 끝났지만 아직 가입 정보를 넣지 않은' 상태 (pending)
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    pending     TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

-- 휴대폰 인증번호 (번호 자체는 저장하지 않고 해시만)
CREATE TABLE IF NOT EXISTS otp_codes (
    id          INTEGER PRIMARY KEY,
    phone       TEXT NOT NULL,
    code_hash   TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used        INTEGER NOT NULL DEFAULT 0,
    ip          TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS otp_phone_idx ON otp_codes (phone, created_at);
CREATE INDEX IF NOT EXISTS otp_ip_idx ON otp_codes (ip, created_at);

-- 카카오 로그인 요청 확인용 (다른 사이트가 끼어드는 것을 막는 state 값)
CREATE TABLE IF NOT EXISTS oauth_states (
    state       TEXT PRIMARY KEY,
    next        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_tips (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tip_id      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, tip_id)
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso(utcnow())


def later_iso(**kwargs) -> str:
    return iso(utcnow() + timedelta(**kwargs))


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(path: Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
