"""명령어 모음.  engine 폴더에서  python -m haruon_engine <명령>  으로 실행한다.

  init      데이터베이스를 만들고 기본 정보·받는 분 목록을 넣는다
  collect   공공데이터를 가져온다
  draft     가져온 자료로 AI 초안을 만든다
  review    약사 검토 화면을 연다 (http://127.0.0.1:8790)
  plan      오늘 받는 분마다 보낼 정보를 고른다
  send      계획대로 보낸다 (지금은 data/outbox 폴더에 파일로)
  daily     collect + draft + plan 을 한 번에 (매일 새벽 예약 실행용)
  status    지금 쌓인 양을 본다
  list / approve / reject   명령어로 검토할 때
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .config import CATEGORIES, ENGINE_DIR, REGIONS, Settings, now_kst
from .db import connect, stamp, tip_dict


def _day(s: str | None) -> date:
    return date.fromisoformat(s) if s else now_kst().date()


def _users(conn, path: Path) -> int:
    users = json.loads(path.read_text(encoding="utf-8"))
    for u in users:
        if u.get("region") and u["region"] not in REGIONS:
            print(f"  ⚠ {u['name']}: 지역 '{u['region']}' 은 config.REGIONS 에 없어서 날씨·미세먼지 정보를 못 받아요")
        conn.execute(
            "INSERT INTO users (id, name, region, interests, plan, active) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, region = excluded.region, "
            "interests = excluded.interests, plan = excluded.plan, active = excluded.active",
            (u["id"], u["name"], u.get("region"), json.dumps(u.get("interests", []), ensure_ascii=False),
             u.get("plan", "free"), 1 if u.get("active", True) else 0))
    conn.commit()
    return len(users)


def cmd_init(args, settings, conn):
    from .seeds import load_seeds
    n = load_seeds(conn)
    print(f"기본 정보 {n}건을 넣었어요 (검토 대기 상태).")
    users_path = Path(args.users) if args.users else ENGINE_DIR / "users.sample.json"
    print(f"받는 분 {_users(conn, users_path)}명을 넣었어요 ({users_path.name}).")
    print(f"데이터 파일: {settings.db_path}")


def cmd_collect(args, settings, conn):
    from .sources import Ctx, run_all
    ctx = Ctx(conn=conn, settings=settings, day=_day(args.date), sample=args.sample)
    print(f"공공데이터 가져오기 ({ctx.day}{', 샘플 자료' if args.sample else ''})")
    for name, result in run_all(ctx, only=args.only).items():
        print(f"  → {name}: {result}")


def cmd_draft(args, settings, conn):
    from .writer import WriterUnavailable, draft_pending
    print("초안 만들기")
    try:
        r = draft_pending(conn, settings, limit=args.limit)
    except WriterUnavailable as e:
        print(f"  실패: {e}")
        return 1
    print(f"  → 초안 {r['drafted']}건, 건너뜀 {r['skipped']}건 (방식: {r['mode']})")


def cmd_plan(args, settings, conn):
    from .planner import plan_day
    day = _day(args.date)
    print(f"{day} 발송 계획")
    results = plan_day(conn, settings, day, dry_run=args.dry_run)
    if args.show:
        for r in results:
            print(f"\n----- {r['user']['name']} -----\n{r['message']}")


def cmd_send(args, settings, conn):
    from .senders import send_day
    day = _day(args.date)
    print(f"{day} 발송 ({args.channel})")
    r = send_day(conn, settings.outbox_dir, day, channel=args.channel)
    print(f"  → 보냄 {r['sent']}명, 보류 {r['held']}명")


def cmd_daily(args, settings, conn):
    cmd_collect(args, settings, conn)
    args.limit = None
    if cmd_draft(args, settings, conn):
        return 1
    cmd_plan(args, settings, conn)
    print("\n다음: 약사 검토(review) 후 승인된 정보로 plan 을 다시 하고 send 하세요.")


def cmd_review(args, settings, conn):
    from .review_server import serve
    conn.close()
    serve(settings, port=args.port)


def cmd_status(args, settings, conn):
    q = lambda sql, *p: conn.execute(sql, p).fetchall()  # noqa: E731
    print("원본 자료:", ", ".join(f"{r['source']} {r['n']}" for r in q(
        "SELECT source, COUNT(*) n FROM raw_items GROUP BY source")) or "없음")
    print("원본 상태:", ", ".join(f"{r['status']} {r['n']}" for r in q(
        "SELECT status, COUNT(*) n FROM raw_items GROUP BY status")) or "없음")
    print("정보 상태:", ", ".join(f"{r['status']} {r['n']}" for r in q(
        "SELECT status, COUNT(*) n FROM tips GROUP BY status")) or "없음")
    print("승인된 정보(주제별):")
    for r in q("SELECT category, COUNT(*) n FROM tips WHERE status = 'approved' AND kind = 'evergreen' GROUP BY category"):
        print(f"  {CATEGORIES.get(r['category'], r['category'])}: {r['n']}")
    print("받는 분:", q("SELECT COUNT(*) n FROM users WHERE active = 1")[0]["n"], "명")
    print("총 발송:", q("SELECT COUNT(*) n FROM sends")[0]["n"], "건")


def cmd_list(args, settings, conn):
    rows = conn.execute("SELECT * FROM tips WHERE status = ? ORDER BY id", (args.status,)).fetchall()
    for r in rows:
        t = tip_dict(r)
        flag = f"  ⚠ {'; '.join(t['flags'])}" if t["flags"] else ""
        print(f"#{t['id']} [{CATEGORIES.get(t['category'])}] {t['title']}{flag}")
    print(f"({len(rows)}건)")


def cmd_approve(args, settings, conn):
    if args.all_drafts:
        print("⚠ 검토 없이 모든 초안을 승인합니다. 테스트할 때만 쓰세요.")
        cur = conn.execute("UPDATE tips SET status = 'approved', reviewed_at = ?, review_note = '일괄 승인(테스트)' "
                           "WHERE status = 'draft'", (stamp(),))
    else:
        marks = ",".join("?" * len(args.ids))
        cur = conn.execute(f"UPDATE tips SET status = 'approved', reviewed_at = ? WHERE id IN ({marks})",
                           (stamp(), *args.ids))
    conn.commit()
    print(f"승인 {cur.rowcount}건")


def cmd_reject(args, settings, conn):
    cur = conn.execute("UPDATE tips SET status = 'rejected', reviewed_at = ?, review_note = ? WHERE id = ?",
                       (stamp(), args.note, args.id))
    conn.commit()
    print(f"반려 {cur.rowcount}건")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m haruon_engine", description="건강한통 콘텐츠 엔진")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="데이터베이스 만들기, 기본 정보·받는 분 넣기")
    s.add_argument("--users", help="받는 분 목록 JSON (기본: users.sample.json)")
    s.set_defaults(fn=cmd_init)

    for name, fn, helptext in (("collect", cmd_collect, "공공데이터 가져오기"),
                               ("daily", cmd_daily, "collect + draft + plan")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--sample", action="store_true", help="API 대신 samples 폴더의 예시 응답 사용")
        s.add_argument("--only", choices=["weather", "air", "drug_easy", "dur_elderly", "gov24"])
        s.add_argument("--date", help="YYYY-MM-DD (기본: 오늘)")
        s.add_argument("--show", action="store_true", help="(daily) 만든 메시지 보여 주기")
        s.add_argument("--dry-run", action="store_true", help="(daily) 계획을 저장하지 않기")
        s.set_defaults(fn=fn)

    s = sub.add_parser("draft", help="AI 초안 만들기")
    s.add_argument("--limit", type=int)
    s.set_defaults(fn=cmd_draft)

    s = sub.add_parser("plan", help="오늘 보낼 정보 고르기")
    s.add_argument("--date")
    s.add_argument("--show", action="store_true", help="메시지 전체 보기")
    s.add_argument("--dry-run", action="store_true", help="저장하지 않고 보기만")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("send", help="계획대로 보내기")
    s.add_argument("--date")
    s.add_argument("--channel", choices=["file", "kakao"], default="file")
    s.set_defaults(fn=cmd_send)

    s = sub.add_parser("review", help="약사 검토 화면 열기")
    s.add_argument("--port", type=int, default=8790)
    s.set_defaults(fn=cmd_review)

    sub.add_parser("status", help="쌓인 양 보기").set_defaults(fn=cmd_status)

    s = sub.add_parser("list", help="정보 목록")
    s.add_argument("--status", default="draft", choices=["draft", "approved", "rejected"])
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("approve", help="승인")
    s.add_argument("ids", nargs="*", type=int)
    s.add_argument("--all-drafts", action="store_true", help="모든 초안 일괄 승인 (테스트용)")
    s.set_defaults(fn=cmd_approve)

    s = sub.add_parser("reject", help="반려")
    s.add_argument("id", type=int)
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_reject)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    args = build_parser().parse_args(argv)
    if args.cmd == "approve" and not args.ids and not args.all_drafts:
        print("승인할 번호를 적거나 --all-drafts 를 쓰세요.")
        return 2
    settings = Settings.from_env()
    conn = connect(settings.db_path)
    try:
        return args.fn(args, settings, conn) or 0
    finally:
        try:
            conn.close()
        except Exception:
            pass
