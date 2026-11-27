"""로그인: 세션 쿠키, 휴대폰 인증번호, 카카오 로그인."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from fastapi import HTTPException, Request, Response

from .db import iso, later_iso, now_iso, utcnow

log = logging.getLogger("ght.auth")

COOKIE = "ght_session"
OTP_TTL_MIN = 5            # 인증번호 유효 시간
OTP_MAX_ATTEMPTS = 5       # 틀릴 수 있는 횟수
OTP_COOLDOWN_SEC = 60      # 다시 받기까지 기다리는 시간
OTP_DAILY_PER_PHONE = 10   # 한 번호로 하루에 받을 수 있는 횟수
OTP_HOURLY_PER_IP = 20     # 한 접속지에서 한 시간에 요청할 수 있는 횟수
PENDING_TTL_MIN = 30       # 본인 확인 후 가입 정보를 넣기까지 기다리는 시간
STATE_TTL_MIN = 10         # 카카오 로그인 요청 유효 시간

SAFE_NEXT = re.compile(r"^(index|my|membership)\.html(#[a-z]+)?$")


def fail(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def safe_next(value: str | None) -> str:
    return value if value and SAFE_NEXT.match(value) else "my.html"


def normalize_phone(value: str) -> str:
    d = re.sub(r"\D", "", value or "")
    if not re.fullmatch(r"01[016789]\d{7,8}", d):
        raise fail(400, "bad_phone", "휴대폰 번호를 다시 확인해 주세요. 예: 010-1234-5678")
    return f"{d[:3]}-{d[3:-4]}-{d[-4:]}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, settings, sms):
        self.s = settings
        self.sms = sms

    # ------------------------------------------------------------------ 세션
    def read_session(self, conn: sqlite3.Connection, request: Request):
        token = request.cookies.get(COOKIE)
        if not token:
            return None
        row = conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (_token_hash(token),)).fetchone()
        if not row or row["expires_at"] <= now_iso():
            return None
        return row

    def current_user(self, conn: sqlite3.Connection, request: Request, response: Response | None = None):
        sess = self.read_session(conn, request)
        if not sess or sess["user_id"] is None:
            return None
        user = conn.execute("SELECT * FROM users WHERE id = ?", (sess["user_id"],)).fetchone()
        if user is None:
            return None
        # 쓰는 동안에는 로그인이 계속 유지되도록 만료일을 하루에 한 번 늘린다
        if sess["expires_at"] < later_iso(days=self.s.session_days - 1):
            conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                         (later_iso(days=self.s.session_days), sess["token_hash"]))
            conn.commit()
            if response is not None:   # 브라우저 쿠키 기한도 함께 늘린다
                response.set_cookie(COOKIE, request.cookies[COOKIE], max_age=self.s.session_days * 86400,
                                    httponly=True, secure=self.s.cookie_secure, samesite="lax", path="/")
        return user

    def require_user(self, conn, request):
        user = self.current_user(conn, request)
        if user is None:
            raise fail(401, "login_required", "로그인이 필요해요.")
        return user

    def start_session(self, conn, request: Request, response: Response, *, user_id=None, pending=None) -> None:
        old = request.cookies.get(COOKIE)
        if old:  # 로그인할 때마다 새 토큰으로 바꾼다
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(old),))
        token = secrets.token_urlsafe(32)
        if user_id is not None:
            expires, max_age = later_iso(days=self.s.session_days), self.s.session_days * 86400
        else:
            expires, max_age = later_iso(minutes=PENDING_TTL_MIN), PENDING_TTL_MIN * 60
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, pending, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (_token_hash(token), user_id, json.dumps(pending, ensure_ascii=False) if pending else None, now_iso(), expires))
        conn.commit()
        response.set_cookie(COOKIE, token, max_age=max_age, httponly=True, secure=self.s.cookie_secure,
                            samesite="lax", path="/")

    def end_session(self, conn, request: Request, response: Response) -> None:
        token = request.cookies.get(COOKIE)
        if token:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
            conn.commit()
        response.delete_cookie(COOKIE, path="/")

    def pending(self, conn, request) -> dict | None:
        sess = self.read_session(conn, request)
        if not sess or sess["user_id"] is not None or not sess["pending"]:
            return None
        return json.loads(sess["pending"])

    # --------------------------------------------------------- 휴대폰 인증
    def _code_hash(self, phone: str, code: str) -> str:
        return hmac.new(self.s.secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()

    def send_code(self, conn, phone: str, ip: str) -> None:
        now = utcnow()
        last = conn.execute("SELECT created_at FROM otp_codes WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
        if last and last["created_at"] > iso(now - timedelta(seconds=OTP_COOLDOWN_SEC)):
            raise fail(429, "cooldown", "인증번호를 방금 보냈어요. 1분 뒤에 다시 받아 주세요.")
        day = conn.execute("SELECT COUNT(*) FROM otp_codes WHERE phone = ? AND created_at > ?",
                           (phone, iso(now - timedelta(days=1)))).fetchone()[0]
        if day >= OTP_DAILY_PER_PHONE:
            raise fail(429, "daily_limit", "오늘은 인증번호를 많이 받으셨어요. 내일 다시 해 주세요.")
        hour = conn.execute("SELECT COUNT(*) FROM otp_codes WHERE ip = ? AND created_at > ?",
                            (ip, iso(now - timedelta(hours=1)))).fetchone()[0]
        if hour >= OTP_HOURLY_PER_IP:
            raise fail(429, "ip_limit", "요청이 너무 많아요. 잠시 뒤에 다시 해 주세요.")

        code = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute("UPDATE otp_codes SET used = 1 WHERE phone = ? AND used = 0", (phone,))
        cur = conn.execute("INSERT INTO otp_codes (phone, code_hash, ip, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                           (phone, self._code_hash(phone, code), ip, iso(now), iso(now + timedelta(minutes=OTP_TTL_MIN))))
        conn.commit()
        try:
            self.sms.send(phone, f"[건강한통] 인증번호 {code} (5분 안에 입력해 주세요)")
        except Exception:
            # 문자가 안 나갔으면 기록을 지워, '방금 보냈어요'로 막히지 않고 바로 다시 시도할 수 있게 한다
            conn.execute("DELETE FROM otp_codes WHERE id = ?", (cur.lastrowid,))
            conn.commit()
            raise

    def check_code(self, conn, phone: str, code: str) -> None:
        row = conn.execute("SELECT * FROM otp_codes WHERE phone = ? AND used = 0 ORDER BY id DESC LIMIT 1",
                           (phone,)).fetchone()
        if row is None:
            raise fail(400, "no_code", "인증번호를 먼저 받아 주세요.")
        if row["expires_at"] <= now_iso():
            conn.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            raise fail(410, "expired", "인증번호 시간이 지났어요. ‘다시 보내기’를 눌러 새 번호를 받아 주세요.")
        if row["attempts"] >= OTP_MAX_ATTEMPTS:
            raise fail(429, "locked", "여러 번 틀려서 이 인증번호는 더 쓸 수 없어요. 새 번호를 받아 주세요.")
        if not hmac.compare_digest(row["code_hash"], self._code_hash(phone, (code or "").strip())):
            attempts = row["attempts"] + 1
            conn.execute("UPDATE otp_codes SET attempts = ? WHERE id = ?", (attempts, row["id"]))
            conn.commit()
            left = OTP_MAX_ATTEMPTS - attempts
            if left <= 0:
                raise fail(429, "locked", "여러 번 틀려서 이 인증번호는 더 쓸 수 없어요. 새 번호를 받아 주세요.")
            raise fail(400, "wrong_code", f"번호가 맞지 않아요. {left}번 더 넣어 보실 수 있어요.", remaining=left)
        conn.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (row["id"],))
        conn.commit()

    # -------------------------------------------------------------- 카카오
    def new_state(self, conn, next_page: str) -> str:
        state = secrets.token_urlsafe(24)
        conn.execute("DELETE FROM oauth_states WHERE created_at < ?", (iso(utcnow() - timedelta(minutes=STATE_TTL_MIN)),))
        conn.execute("INSERT INTO oauth_states (state, next, created_at) VALUES (?, ?, ?)", (state, next_page, now_iso()))
        conn.commit()
        return state

    def take_state(self, conn, state: str | None) -> str | None:
        if not state:
            return None
        row = conn.execute("SELECT * FROM oauth_states WHERE state = ?", (state,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
        if row["created_at"] < iso(utcnow() - timedelta(minutes=STATE_TTL_MIN)):
            return None
        return row["next"]

    def kakao_authorize_url(self, state: str) -> str:
        return "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": self.s.kakao_rest_key,
            "redirect_uri": self.s.kakao_redirect_uri, "state": state})

    def kakao_profile(self, code: str) -> tuple[str, str]:
        """인가 코드로 토큰을 받고 회원 번호와 이름(닉네임)을 가져온다."""
        form = {"grant_type": "authorization_code", "client_id": self.s.kakao_rest_key,
                "redirect_uri": self.s.kakao_redirect_uri, "code": code}
        if self.s.kakao_client_secret:
            form["client_secret"] = self.s.kakao_client_secret
        token = self._kakao_call("https://kauth.kakao.com/oauth/token", data=urllib.parse.urlencode(form).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
        me = self._kakao_call("https://kapi.kakao.com/v2/user/me",
                              headers={"Authorization": f"Bearer {token['access_token']}"})
        kakao_id = str(me["id"])
        profile = (me.get("kakao_account") or {}).get("profile") or {}
        nickname = profile.get("nickname") or (me.get("properties") or {}).get("nickname") or ""
        return kakao_id, nickname

    @staticmethod
    def _kakao_call(url: str, data: bytes | None = None, headers: dict | None = None) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            log.error("카카오 요청 실패 %s: %s", url, e.read().decode("utf-8", errors="replace")[:300])
            raise
