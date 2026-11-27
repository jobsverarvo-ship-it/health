"""건강한통 웹 서버.

실행:  python -m uvicorn server.main:app --port 8000
사이트 파일(index.html 등)도 이 서버가 함께 보여 준다.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import sqlite3
import urllib.parse
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import db, tips as tips_mod
from .auth import Auth, fail, normalize_phone, safe_next
from .config import ROOT, Settings
from .sms import SmsError, make_sender

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ght")

INTERESTS = {"혈압", "당뇨", "관절·뼈", "심장", "눈", "귀", "기억력", "수면", "소화", "특별히 없어요"}
PAGES = ["index.html", "start.html", "my.html", "membership.html"]


# ---------------------------------------------------------------- 요청 형식
class PhoneIn(BaseModel):
    phone: str = Field(max_length=20)


class VerifyIn(BaseModel):
    phone: str = Field(max_length=20)
    code: str = Field(max_length=10)


def _check_interests(v: list[str]) -> list[str]:
    v = [x for x in dict.fromkeys(v) if x in INTERESTS]
    if not v:
        raise ValueError("관심 건강을 하나 이상 골라 주세요.")
    if "특별히 없어요" in v and len(v) > 1:
        v = [x for x in v if x != "특별히 없어요"]
    return v


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    interests: list[str] = Field(max_length=12)
    channel: Literal["kakao", "sms"]
    time: Literal["7", "8", "9"]
    agree_terms: bool
    agree_privacy: bool
    agree_health: bool
    marketing: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("이름을 적어 주세요.")
        return v

    @field_validator("interests")
    @classmethod
    def _interests(cls, v: list[str]) -> list[str]:
        return _check_interests(v)


class MePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=20)
    interests: Optional[list[str]] = Field(default=None, max_length=12)
    channel: Optional[Literal["kakao", "sms"]] = None
    time: Optional[Literal["7", "8", "9"]] = None
    paused: Optional[bool] = None

    @field_validator("interests")
    @classmethod
    def _interests(cls, v):
        return None if v is None else _check_interests(v)


def public_user(row: sqlite3.Row) -> dict:
    return {
        "name": row["name"],
        "method": "kakao" if row["kakao_id"] else "phone",
        "phone": row["phone"],
        "interests": json.loads(row["interests"]),
        "channel": row["channel"],
        "time": row["send_time"],
        "paused": bool(row["paused"]),
        "plan": row["plan"],
        "joined_at": row["created_at"],
    }


# ---------------------------------------------------------------- 앱 만들기
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    db.init(settings.db_path)
    sms = make_sender(settings)
    auth = Auth(settings, sms)
    all_tips = tips_mod.load(ROOT)
    tip_ids = {t["id"] for t in all_tips}

    app = FastAPI(title="건강한통", docs_url="/api/docs" if settings.dev else None, redoc_url=None, openapi_url="/api/openapi.json" if settings.dev else None)
    app.state.settings, app.state.sms, app.state.auth = settings, sms, auth

    def get_conn():
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------ 보안: 다른 사이트에서 보낸 요청 막기 + 보안 헤더
    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE") and path != "/api/auth/kakao/practice":
            if request.headers.get("x-requested-with") != "ght":
                return JSONResponse({"detail": {"code": "forbidden", "message": "잘못된 요청이에요."}}, status_code=403)
            origin = request.headers.get("origin")
            own = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin and origin.rstrip("/") not in (own, settings.public_url):
                return JSONResponse({"detail": {"code": "forbidden", "message": "잘못된 요청이에요."}}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if settings.dev and path == "/api/docs":   # 개발용 API 안내 화면은 외부 스크립트를 쓴다
            return response
        response.headers.setdefault("Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
            "form-action 'self'")
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    # ------------------------------------------------ 설정
    @app.get("/api/config")
    def config():
        return {
            "kakao": settings.kakao_enabled or settings.dev,
            "kakao_practice": settings.dev and not settings.kakao_enabled,
            "sms_console": settings.sms_provider == "console",
        }

    # ------------------------------------------------ 휴대폰 인증
    @app.post("/api/auth/phone/start")
    def phone_start(body: PhoneIn, request: Request, conn=Depends(get_conn)):
        phone = normalize_phone(body.phone)
        try:
            auth.send_code(conn, phone, client_ip(request))
        except SmsError:
            raise fail(502, "sms_failed", "문자를 보내지 못했어요. 잠시 뒤에 다시 해 주세요.")
        return {"sent": True, "phone": phone, "console": settings.sms_provider == "console"}

    @app.post("/api/auth/phone/verify")
    def phone_verify(body: VerifyIn, request: Request, response: Response, conn=Depends(get_conn)):
        phone = normalize_phone(body.phone)
        auth.check_code(conn, phone, body.code)
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        if user:
            auth.start_session(conn, request, response, user_id=user["id"])
            return {"status": "logged_in", "user": public_user(user)}
        auth.start_session(conn, request, response, pending={"method": "phone", "phone": phone})
        return {"status": "needs_profile", "pending": {"method": "phone", "phone": phone}}

    # ------------------------------------------------ 카카오 로그인
    def finish_kakao(conn, request: Request, kakao_id: str, nickname: str, next_page: str):
        user = conn.execute("SELECT * FROM users WHERE kakao_id = ?", (kakao_id,)).fetchone()
        if user:
            resp = RedirectResponse("/" + next_page, status_code=303)
            auth.start_session(conn, request, resp, user_id=user["id"])
            return resp
        resp = RedirectResponse(f"/start.html?step=profile&next={next_page}", status_code=303)
        auth.start_session(conn, request, resp, pending={"method": "kakao", "kakao_id": kakao_id, "name_hint": nickname[:20]})
        return resp

    @app.get("/api/auth/kakao/start")
    def kakao_start(next: str | None = None, conn=Depends(get_conn)):
        state = auth.new_state(conn, safe_next(next))
        if settings.kakao_enabled:
            return RedirectResponse(auth.kakao_authorize_url(state), status_code=302)
        if settings.dev:
            return RedirectResponse(f"/api/auth/kakao/practice?state={state}", status_code=302)
        return RedirectResponse("/start.html?error=kakao_unavailable", status_code=302)

    @app.get("/api/auth/kakao/callback")
    def kakao_callback(request: Request, code: str | None = None, state: str | None = None,
                       error: str | None = None, conn=Depends(get_conn)):
        next_page = auth.take_state(conn, state)
        if error:
            return RedirectResponse("/start.html?error=kakao_cancel", status_code=303)
        if not next_page or not code:
            return RedirectResponse("/start.html?error=kakao_state", status_code=303)
        try:
            kakao_id, nickname = auth.kakao_profile(code)
        except Exception:
            log.exception("카카오 로그인 실패")
            return RedirectResponse("/start.html?error=kakao_failed", status_code=303)
        return finish_kakao(conn, request, kakao_id, nickname, next_page)

    # 개발용 연습 화면: 카카오 앱 키가 없을 때만, 개발 환경에서만 열린다
    @app.get("/api/auth/kakao/practice", response_class=HTMLResponse)
    def kakao_practice_page(state: str = ""):
        if not settings.dev or settings.kakao_enabled:
            raise fail(404, "not_found", "없는 페이지예요.")
        s = html.escape(state)
        return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>카카오 로그인 연습</title><link rel="stylesheet" href="/assets/css/site.css"></head><body>
<main class="app-main"><div class="wrap wrap-narrow"><section class="panel">
<p class="chip" style="margin-bottom:1rem">개발용 연습 화면</p>
<h1 class="page-title">카카오 로그인 연습</h1>
<p class="page-sub">카카오 앱 키를 넣기 전이라, 실제 카카오 대신 이 화면이 열려요. 카카오에 등록된 이름이라고 생각하고 적어 주세요. 같은 이름으로 다시 들어오면 같은 사람으로 로그인돼요.</p>
<form method="post" action="/api/auth/kakao/practice" class="step-body">
<input type="hidden" name="state" value="{s}">
<div class="field"><label for="n">카카오 이름</label><input id="n" name="nickname" required maxlength="20" placeholder="예: 김순자"></div>
<button class="btn btn-kakao btn-lg btn-block" type="submit">동의하고 계속하기</button>
<a class="btn-text" href="/start.html" style="text-align:center">취소</a>
</form></section></div></main></body></html>"""

    @app.post("/api/auth/kakao/practice")
    async def kakao_practice_submit(request: Request, conn=Depends(get_conn)):
        if not settings.dev or settings.kakao_enabled:
            raise fail(404, "not_found", "없는 페이지예요.")
        form = urllib.parse.parse_qs((await request.body()).decode("utf-8", errors="replace"))
        state = (form.get("state") or [""])[0]
        nickname = (form.get("nickname") or [""])[0].strip()[:20]
        next_page = auth.take_state(conn, state)
        if not next_page or not nickname:
            return RedirectResponse("/start.html?error=kakao_state", status_code=303)
        fake_id = "practice-" + hashlib.sha256(nickname.encode()).hexdigest()[:16]
        return finish_kakao(conn, request, fake_id, nickname, next_page)

    # ------------------------------------------------ 가입 마무리
    @app.get("/api/auth/pending")
    def pending(request: Request, conn=Depends(get_conn)):
        p = auth.pending(conn, request)
        if not p:
            raise fail(404, "no_pending", "본인 확인부터 다시 해 주세요.")
        return {"method": p["method"], "phone": p.get("phone"), "name_hint": p.get("name_hint", "")}

    @app.post("/api/auth/signup")
    def signup(body: SignupIn, request: Request, response: Response, conn=Depends(get_conn)):
        p = auth.pending(conn, request)
        if not p:
            raise fail(401, "no_pending", "본인 확인 시간이 지났어요. 처음부터 다시 해 주세요.")
        if not (body.agree_terms and body.agree_privacy and body.agree_health):
            raise fail(400, "consent_required", "[필수] 항목에 모두 동의해 주셔야 가입할 수 있어요.")
        if p["method"] == "kakao" and body.channel == "sms":
            raise fail(400, "sms_needs_phone", "문자로 받으시려면 휴대폰 번호로 가입해 주세요.")
        now = db.now_iso()
        column, value = ("phone", p["phone"]) if p["method"] == "phone" else ("kakao_id", p["kakao_id"])
        existing = conn.execute(f"SELECT * FROM users WHERE {column} = ?", (value,)).fetchone()
        if existing is None:
            cur = conn.execute(
                f"INSERT INTO users (name, {column}, interests, channel, send_time, marketing, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (body.name, value, json.dumps(body.interests, ensure_ascii=False), body.channel, body.time,
                 int(body.marketing), now, now))
            user_id = cur.lastrowid
            for item, agreed in (("terms", True), ("privacy", True), ("health", True), ("marketing", body.marketing)):
                conn.execute("INSERT INTO consents (user_id, item, agreed, created_at) VALUES (?, ?, ?, ?)",
                             (user_id, item, int(agreed), now))
            conn.commit()
        else:
            user_id = existing["id"]
        auth.start_session(conn, request, response, user_id=user_id)
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return {"user": public_user(user)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, conn=Depends(get_conn)):
        auth.end_session(conn, request, response)
        return {"ok": True}

    # ------------------------------------------------ 내 정보
    @app.get("/api/session")
    def session(request: Request, response: Response, conn=Depends(get_conn)):
        """화면이 로그인 여부를 물어볼 때 쓴다. 로그인 안 했으면 user 가 null (오류 아님)."""
        user = auth.current_user(conn, request, response)
        return {"user": public_user(user) if user else None}

    @app.get("/api/me")
    def me(request: Request, conn=Depends(get_conn)):
        return {"user": public_user(auth.require_user(conn, request))}

    @app.patch("/api/me")
    def update_me(body: MePatch, request: Request, conn=Depends(get_conn)):
        user = auth.require_user(conn, request)
        changes = {}
        if body.name is not None:
            changes["name"] = body.name.strip()
        if body.interests is not None:
            changes["interests"] = json.dumps(body.interests, ensure_ascii=False)
        if body.channel is not None:
            if body.channel == "sms" and not user["phone"]:
                raise fail(400, "sms_needs_phone", "문자로 받으시려면 휴대폰 번호가 있어야 해요. 지금은 카카오톡으로 받으실 수 있어요.")
            changes["channel"] = body.channel
        if body.time is not None:
            changes["send_time"] = body.time
        if body.paused is not None:
            changes["paused"] = int(body.paused)
        if changes:
            changes["updated_at"] = db.now_iso()
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE users SET {sets} WHERE id = ?", (*changes.values(), user["id"]))
            conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return {"user": public_user(row)}

    @app.delete("/api/me")
    def delete_me(request: Request, response: Response, conn=Depends(get_conn)):
        user = auth.require_user(conn, request)
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))   # 세션, 동의 기록, 저장한 정보도 함께 지워진다
        conn.commit()
        response.delete_cookie("ght_session", path="/")
        return {"ok": True}

    # ------------------------------------------------ 건강정보함
    @app.get("/api/tips")
    def tips(request: Request, conn=Depends(get_conn)):
        auth.require_user(conn, request)
        return {"tips": tips_mod.with_dates(all_tips)}

    def saved_ids(conn, user_id) -> list[str]:
        return [r["tip_id"] for r in conn.execute(
            "SELECT tip_id FROM saved_tips WHERE user_id = ? ORDER BY created_at", (user_id,))]

    @app.get("/api/me/saved")
    def saved(request: Request, conn=Depends(get_conn)):
        user = auth.require_user(conn, request)
        return {"ids": saved_ids(conn, user["id"])}

    @app.put("/api/me/saved/{tip_id}")
    def save_tip(tip_id: str, request: Request, conn=Depends(get_conn)):
        user = auth.require_user(conn, request)
        if tip_id not in tip_ids:
            raise fail(404, "no_tip", "없는 정보예요.")
        conn.execute("INSERT OR IGNORE INTO saved_tips (user_id, tip_id, created_at) VALUES (?, ?, ?)",
                     (user["id"], tip_id, db.now_iso()))
        conn.commit()
        return {"ids": saved_ids(conn, user["id"])}

    @app.delete("/api/me/saved/{tip_id}")
    def unsave_tip(tip_id: str, request: Request, conn=Depends(get_conn)):
        user = auth.require_user(conn, request)
        conn.execute("DELETE FROM saved_tips WHERE user_id = ? AND tip_id = ?", (user["id"], tip_id))
        conn.commit()
        return {"ids": saved_ids(conn, user["id"])}

    # ------------------------------------------------ 사이트 파일 (정해 둔 것만 보여 준다)
    app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")

    def page(name: str):
        def handler():
            return FileResponse(ROOT / name, media_type="text/html", headers={"Cache-Control": "no-cache"})
        return handler

    app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)(page("index.html"))
    for name in PAGES:
        app.api_route(f"/{name}", methods=["GET", "HEAD"], include_in_schema=False)(page(name))

    return app


app = create_app()
