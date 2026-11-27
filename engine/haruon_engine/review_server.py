"""약사 검토 화면 (내 컴퓨터에서만 열리는 작은 웹페이지).

python -m haruon_engine review  →  http://127.0.0.1:8790
- 검토 대기: AI·규칙 초안과 기본 정보를 고치고 승인하거나 반려
- 승인됨: 발송 대상이 된 정보 목록
- 오늘 발송 미리 보기: 받는 분마다 오늘 어떤 메시지가 갈지 (저장하지 않음)
"""
from __future__ import annotations

import html
import json
import secrets
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import CATEGORIES, TAGS, Settings, now_kst
from .db import connect, stamp, tip_dict
from .planner import plan_day

WRITER_LABEL = {"ai": "AI 초안", "rule": "규칙 초안", "seed": "기본 정보", "template": "날씨·미세먼지 틀"}

CSS = """
:root{--paper:#FBF8F3;--sand:#F4EEE4;--line:#E2D7C5;--ink:#2A221C;--ink2:#594E45;--ink3:#7A6D62;
--cocoa:#3A2C22;--gold:#8A683D;--alert:#93412F;color-scheme:light}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:"Noto Sans KR","Malgun Gothic",system-ui,sans-serif;font-size:17px;line-height:1.65;word-break:keep-all}
.wrap{max-width:860px;margin:0 auto;padding:0 20px}
header{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.bar{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:center;justify-content:space-between;min-height:60px}
nav{display:flex;flex-wrap:wrap;gap:6px 18px}nav a{color:var(--ink2);text-decoration:none}nav a:hover{color:var(--ink)}
.n{display:inline-block;min-width:1.6em;padding:0 .4em;border-radius:99px;background:var(--sand);text-align:center;font-size:.85em;font-weight:700}
h1{font-size:1.4rem;margin:32px 0 8px}p.lead{color:var(--ink2);margin:0 0 24px}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:22px;margin:0 0 20px;display:grid;gap:12px}
.meta{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;font-size:.85rem;color:var(--ink3)}
.chip{background:var(--sand);color:var(--gold);font-weight:700;border-radius:99px;padding:2px 10px}
.flags{margin:0;padding:10px 14px 10px 30px;background:#FBEDE8;color:var(--alert);border-radius:12px;font-size:.9rem}
label{display:grid;gap:4px;font-size:.85rem;font-weight:700;color:var(--ink2)}
input,textarea,select{font:inherit;font-weight:400;color:var(--ink);border:1.5px solid #D5C8B4;border-radius:10px;padding:9px 12px;background:#fff;width:100%}
textarea{resize:vertical}input:focus,textarea:focus,select:focus{outline:none;border-color:var(--cocoa)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:640px){.row{grid-template-columns:1fr}}
details{font-size:.85rem;color:var(--ink2)}pre{white-space:pre-wrap;background:var(--sand);padding:12px;border-radius:10px;font-size:.82rem;max-height:260px;overflow:auto}
.actions{display:flex;flex-wrap:wrap;gap:8px}
button{font:inherit;font-weight:700;border-radius:99px;padding:10px 18px;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
button.primary{background:var(--cocoa);color:#F7F1E8;border-color:var(--cocoa)}button.danger{color:var(--alert);border-color:#E3C3B8}
.empty{padding:40px;text-align:center;color:var(--ink3);background:#fff;border:1px dashed var(--line);border-radius:18px}
table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.msg{white-space:pre-wrap;background:#fff;border:1px solid var(--line);border-radius:4px 18px 18px 18px;padding:16px;font-size:.95rem;margin:8px 0 24px;max-width:460px}
.who{font-weight:700;margin-top:18px}
"""


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def make_handler(settings: Settings):
    token = secrets.token_urlsafe(16)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # 콘솔을 조용히
            pass

        # -- 공통 ---------------------------------------------------------
        def _conn(self):
            return connect(settings.db_path)

        def _send(self, body: str, status: int = 200):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _page(self, conn, title: str, body: str) -> str:
            c = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) n FROM tips GROUP BY status")}
            return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                    f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                    f"<title>{esc(title)} · 건강한통 검토</title><style>{CSS}</style></head><body>"
                    f'<header><div class="wrap bar"><b>건강한통 콘텐츠 검토</b><nav>'
                    f'<a href="/">검토 대기 <span class="n">{c.get("draft", 0)}</span></a>'
                    f'<a href="/approved">승인됨 <span class="n">{c.get("approved", 0)}</span></a>'
                    f'<a href="/preview">오늘 발송 미리 보기</a></nav></div></header>'
                    f'<main class="wrap">{body}</main></body></html>')

        # -- 화면 ---------------------------------------------------------
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            conn = self._conn()
            try:
                if url.path == "/":
                    self._send(self._page(conn, "검토 대기", self._drafts(conn)))
                elif url.path == "/approved":
                    self._send(self._page(conn, "승인됨", self._approved(conn)))
                elif url.path == "/preview":
                    day = q.get("date", [now_kst().date().isoformat()])[0]
                    self._send(self._page(conn, "발송 미리 보기", self._preview(conn, day)))
                else:
                    self._send(self._page(conn, "없는 페이지", '<p class="lead">없는 페이지예요.</p>'), 404)
            finally:
                conn.close()

        def _drafts(self, conn) -> str:
            rows = conn.execute("SELECT * FROM tips WHERE status = 'draft' ORDER BY priority DESC, id").fetchall()
            head = ('<h1>검토 대기</h1><p class="lead">문장을 고친 뒤 승인하면 발송 대상이 돼요. '
                    '경고가 붙은 정보는 특히 꼼꼼히 봐 주세요.</p>')
            if not rows:
                return head + '<div class="empty">검토할 정보가 없어요.</div>'
            cards = []
            for r in rows:
                t = tip_dict(r)
                raw = conn.execute("SELECT payload FROM raw_items WHERE id = ?", (t["raw_id"],)).fetchone() if t["raw_id"] else None
                cat_opts = "".join(
                    f'<option value="{k}"{" selected" if k == t["category"] else ""}>{esc(v)}</option>'
                    for k, v in CATEGORIES.items())
                flags = ("<ul class='flags'>" + "".join(f"<li>{esc(f)}</li>" for f in t["flags"]) + "</ul>") if t["flags"] else ""
                raw_html = ""
                if raw:
                    pretty = json.dumps(json.loads(raw["payload"]), ensure_ascii=False, indent=1)
                    link = f' · <a href="{esc(t["source_url"])}" target="_blank" rel="noopener">출처 열기</a>' if t["source_url"] else ""
                    raw_html = f"<details><summary>공공데이터 원문 보기{link}</summary><pre>{esc(pretty)}</pre></details>"
                region = f" · {esc(t['region'])} {esc(t['valid_from'])}" if t["region"] else ""
                cards.append(f"""
<form class="card" id="tip-{t['id']}" method="post" action="/tip/{t['id']}">
  <input type="hidden" name="token" value="{token}">
  <div class="meta"><span class="chip">{esc(CATEGORIES.get(t['category'], t['category']))}</span>
    <span>#{t['id']} · {esc(WRITER_LABEL.get(t['writer'], t['writer']))} · {esc(t['source_name'])}{region}</span></div>
  {flags}
  <div class="row">
    <label>분류<select name="category">{cat_opts}</select></label>
    <label>관심 태그 (쉼표로 구분)<input name="tags" value="{esc(', '.join(t['tags']))}"></label>
  </div>
  <label>제목<input name="title" value="{esc(t['title'])}"></label>
  <label>내용<textarea name="body" rows="3">{esc(t['body'])}</textarea></label>
  <label>오늘 이렇게 해 보세요<input name="action" value="{esc(t['action'])}"></label>
  <label>주의 문구 (없으면 비워 두기)<input name="caution" value="{esc(t['caution'])}"></label>
  {raw_html}
  <label>검토 메모<input name="note" placeholder="반려 이유나 고친 점"></label>
  <div class="actions">
    <button class="primary" name="op" value="approve">이 내용으로 승인</button>
    <button name="op" value="save">저장만</button>
    <button class="danger" name="op" value="reject">반려</button>
  </div>
</form>""")
            return head + "".join(cards)

        def _approved(self, conn) -> str:
            rows = conn.execute("SELECT * FROM tips WHERE status = 'approved' ORDER BY reviewed_at DESC, id DESC LIMIT 200").fetchall()
            if not rows:
                return '<h1>승인됨</h1><div class="empty">아직 승인된 정보가 없어요.</div>'
            trs = []
            for r in rows:
                t = tip_dict(r)
                sent = conn.execute("SELECT COUNT(*) FROM sends WHERE tip_id = ?", (t["id"],)).fetchone()[0]
                when = f"{esc(t['region'])} {esc(t['valid_from'])}" if t["region"] else "언제든"
                trs.append(
                    f"<tr><td>#{t['id']}</td><td>{esc(CATEGORIES.get(t['category']))}</td><td>{esc(t['title'])}</td>"
                    f"<td>{when}</td><td>{sent}명</td><td><form method='post' action='/tip/{t['id']}'>"
                    f"<input type='hidden' name='token' value='{token}'><button name='op' value='unapprove'>되돌리기</button></form></td></tr>")
            return ('<h1>승인됨</h1><p class="lead">발송 대상인 정보예요. 되돌리면 검토 대기로 돌아가요.</p>'
                    "<div style='overflow-x:auto'><table><tr><th>번호</th><th>분류</th><th>제목</th><th>보낼 수 있는 때</th>"
                    "<th>받은 사람</th><th></th></tr>" + "".join(trs) + "</table></div>")

        def _preview(self, conn, day_s: str) -> str:
            try:
                day = date.fromisoformat(day_s)
            except ValueError:
                day = now_kst().date()
            results = plan_day(conn, settings, day, dry_run=True, log=lambda *_: None)
            head = (f'<h1>{day.month}월 {day.day}일 발송 미리 보기</h1>'
                    '<p class="lead">지금 승인된 정보로 받는 분마다 어떤 메시지가 가는지 보여 줘요. 저장되지는 않아요.</p>')
            if not results:
                sent = conn.execute("SELECT COUNT(*) FROM plans WHERE plan_date = ? AND status = 'sent'",
                                    (day.isoformat(),)).fetchone()[0]
                if sent:
                    return head + f'<div class="empty">이날 발송은 이미 끝났어요 ({sent}명).</div>'
                return head + '<div class="empty">보낼 정보가 없어요. 먼저 정보를 승인해 주세요.</div>'
            return head + "".join(
                f"<div class='who'>{esc(r['user']['name'])} · {'멤버십' if r['user']['plan'] == 'member' else '무료'} · "
                f"{esc(r['user']['region'])}</div><div class='msg'>{esc(r['message'])}</div>" for r in results)

        # -- 저장 ---------------------------------------------------------
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True).items()}
            if form.get("token") != token:
                return self._send("<p>화면이 오래됐어요. 새로고침한 뒤 다시 해 주세요.</p>", 403)
            try:
                tip_id = int(self.path.rstrip("/").split("/")[-1])
            except ValueError:
                return self._send("<p>잘못된 요청이에요.</p>", 400)
            op = form.get("op")
            conn = self._conn()
            try:
                if op in ("approve", "save", "reject"):
                    tags = [t.strip() for t in form.get("tags", "").split(",") if t.strip() in TAGS]
                    category = form.get("category") if form.get("category") in CATEGORIES else None
                    status = {"approve": "approved", "reject": "rejected", "save": "draft"}[op]
                    conn.execute(
                        "UPDATE tips SET title = ?, body = ?, action = ?, caution = ?, tags = ?, "
                        "category = COALESCE(?, category), status = ?, reviewed_at = ?, "
                        "review_note = COALESCE(NULLIF(?, ''), review_note) WHERE id = ?",
                        (form.get("title", "").strip(), form.get("body", "").strip(),
                         form.get("action", "").strip(), form.get("caution", "").strip(),
                         json.dumps(tags, ensure_ascii=False), category, status,
                         stamp() if op != "save" else None, form.get("note", "").strip(), tip_id))
                elif op == "unapprove":
                    conn.execute("UPDATE tips SET status = 'draft' WHERE id = ?", (tip_id,))
                conn.commit()
            finally:
                conn.close()
            back = "/approved" if op == "unapprove" else "/"
            self.send_response(303)
            self.send_header("Location", back)
            self.end_headers()

    return Handler


def serve(settings: Settings, port: int = 8790) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(settings))
    print(f"검토 화면: http://127.0.0.1:{port}  (끄려면 Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
