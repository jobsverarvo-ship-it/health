"""발송. 지금은 파일(outbox)로만 내보낸다.

카카오톡 발송은 카카오 비즈니스 채널 개설과 발송 대행사(예: NHN Cloud, 솔라피 등)
계약이 끝난 뒤 KakaoSender 를 채우면 된다. 나머지 흐름은 그대로 쓴다.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from .db import stamp


class FileSender:
    channel = "file"

    def __init__(self, outbox_dir: Path, day: date):
        self.dir = outbox_dir / day.isoformat()
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(self, user: dict, message: str) -> str:
        path = self.dir / f"{user['id']}.txt"
        path.write_text(message + "\n", encoding="utf-8")
        return str(path)


class KakaoSender:
    channel = "kakao"

    def __init__(self, *_args, **_kwargs):
        raise NotImplementedError(
            "카카오톡 발송은 아직 연결 전이에요. 카카오 비즈니스 채널과 발송 대행사 계약 후 "
            "이 클래스의 send(user, message) 를 구현하세요. 매일 바뀌는 글을 보낼 수 있는 "
            "메시지 종류(알림톡·브랜드 메시지 등)와 발송 시간 규정을 먼저 확인해야 해요.")


def send_day(conn: sqlite3.Connection, outbox_dir: Path, day: date, channel: str = "file", log=print) -> dict:
    d = day.isoformat()
    sender = FileSender(outbox_dir, day) if channel == "file" else KakaoSender()
    plans = conn.execute(
        "SELECT p.*, u.name FROM plans p JOIN users u ON u.id = p.user_id "
        "WHERE p.plan_date = ? AND p.status = 'planned' ORDER BY p.user_id", (d,)).fetchall()
    sent = held = 0
    for p in plans:
        tip_ids = json.loads(p["tip_ids"])
        marks = ",".join("?" * len(tip_ids))
        ok = conn.execute(f"SELECT COUNT(*) FROM tips WHERE id IN ({marks}) AND status = 'approved'",
                          tip_ids).fetchone()[0]
        if ok != len(tip_ids):
            log(f"  {p['name']}: 계획 뒤에 반려된 정보가 있어 보내지 않았어요. plan 을 다시 실행하세요.")
            held += 1
            continue
        where = sender.send({"id": p["user_id"], "name": p["name"]}, p["message"])
        for tid in tip_ids:
            conn.execute("INSERT OR IGNORE INTO sends (user_id, tip_id, send_date, channel) VALUES (?, ?, ?, ?)",
                         (p["user_id"], tid, d, sender.channel))
        conn.execute("UPDATE plans SET status = 'sent' WHERE user_id = ? AND plan_date = ?", (p["user_id"], d))
        conn.commit()
        sent += 1
        log(f"  {p['name']}: 보냄 → {where}")
    conn.execute("INSERT INTO state (key, value) VALUES ('last_send', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (stamp(),))
    conn.commit()
    return {"sent": sent, "held": held}
