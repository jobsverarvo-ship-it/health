"""받는 분마다 오늘 보낼 정보를 고른다.

규칙
1. 약사가 승인한 정보만, 그날 보낼 수 있는 것만 (날짜·지역 조건).
2. 그 사람에게 한 번 보낸 정보는 다시 보내지 않는다.
3. 오늘 날씨·미세먼지처럼 지금 꼭 필요한 정보가 있으면 먼저.
4. 하루에 여러 개를 보낼 때는 서로 다른 주제로.
5. 받는 분의 관심 건강(혈압, 당뇨 등)과 겹치면 우선, 요일 주제도 조금 우선.
6. 최근 일주일에 많이 받은 주제는 조금 뒤로.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date, timedelta

from .config import WEEKDAY_THEME, Settings
from .db import tip_dict
from .messages import format_message


def _jitter(user_id: str, tip_id: int, day: str) -> int:
    """점수가 같은 정보들 사이에서 매일 순서가 조금씩 달라지게 한다 (0~6)."""
    h = hashlib.md5(f"{user_id}:{tip_id}:{day}".encode()).hexdigest()
    return int(h, 16) % 7


def choose(user: sqlite3.Row, tips: list[dict], sent: set[int], recent: Counter,
           n: int, day: date) -> list[dict]:
    d = day.isoformat()
    theme = WEEKDAY_THEME[day.weekday()]
    interests = set(json.loads(user["interests"] or "[]"))

    def score(t: dict) -> int:
        s = t["priority"]
        s += 15 * len(interests & set(t["tags"]))
        s += 10 if t["category"] == theme else 0
        s -= 8 * recent[t["category"]]
        return s + _jitter(user["id"], t["id"], d)

    cands = [t for t in tips
             if t["id"] not in sent and (t["region"] is None or t["region"] == user["region"])]
    ranked = sorted(cands, key=score, reverse=True)

    chosen: list[dict] = []
    cats: set[str] = set()
    live = 0
    for t in ranked:  # 1차: 주제가 겹치지 않게 (오늘 날씨·미세먼지는 2개까지 예외)
        if len(chosen) >= n:
            break
        if t["kind"] == "live" and live < 2:
            chosen.append(t)
            cats.add(t["category"])
            live += 1
        elif t["kind"] != "live" and t["category"] not in cats:
            chosen.append(t)
            cats.add(t["category"])
    for t in ranked:  # 2차: 주제가 모자라면 겹쳐도 채운다
        if len(chosen) >= n:
            break
        if t not in chosen and t["kind"] != "live":
            chosen.append(t)
    return chosen


def plan_day(conn: sqlite3.Connection, settings: Settings, day: date, *,
             dry_run: bool = False, log=print) -> list[dict]:
    d = day.isoformat()
    week_ago = (day - timedelta(days=7)).isoformat()
    tips = [tip_dict(r) for r in conn.execute(
        "SELECT * FROM tips WHERE status = 'approved' "
        "AND (valid_from IS NULL OR valid_from <= ?) AND (valid_until IS NULL OR valid_until >= ?)",
        (d, d))]
    users = conn.execute("SELECT * FROM users WHERE active = 1 ORDER BY id").fetchall()
    results = []
    for u in users:
        done = conn.execute("SELECT status FROM plans WHERE user_id = ? AND plan_date = ?",
                            (u["id"], d)).fetchone()
        if done and done["status"] == "sent":
            log(f"  {u['name']}: 이미 발송함, 건너뜀")
            continue
        n = settings.tips_member if u["plan"] == "member" else settings.tips_free
        sent = {r["tip_id"] for r in conn.execute("SELECT tip_id FROM sends WHERE user_id = ?", (u["id"],))}
        recent = Counter(r["category"] for r in conn.execute(
            "SELECT t.category FROM sends s JOIN tips t ON t.id = s.tip_id "
            "WHERE s.user_id = ? AND s.send_date >= ?", (u["id"], week_ago)))
        chosen = choose(u, tips, sent, recent, n, day)
        # 날씨·미세먼지를 뺀, 아직 안 보낸 승인 정보가 얼마나 남았는지
        left = (sum(1 for t in tips if t["id"] not in sent and t["kind"] != "live")
                - sum(1 for t in chosen if t["kind"] != "live"))
        if not chosen:
            log(f"  {u['name']}: 보낼 정보가 없어요. 승인된 정보가 부족합니다.")
            continue
        message = format_message(day, chosen)
        if not dry_run:
            conn.execute(
                "INSERT INTO plans (user_id, plan_date, tip_ids, message, status) VALUES (?, ?, ?, ?, 'planned') "
                "ON CONFLICT(user_id, plan_date) DO UPDATE SET tip_ids = excluded.tip_ids, "
                "message = excluded.message, status = 'planned'",
                (u["id"], d, json.dumps([t["id"] for t in chosen]), message))
        warn = f"  ⚠ 남은 정보 {left}개뿐" if left < n * 7 else ""
        log(f"  {u['name']} ({'멤버십' if u['plan'] == 'member' else '무료'}, {u['region']}): "
            f"{len(chosen)}개 → " + " / ".join(t["title"] for t in chosen) + warn)
        results.append({"user": dict(u), "tips": chosen, "message": message})
    if not dry_run:
        conn.commit()
    return results
