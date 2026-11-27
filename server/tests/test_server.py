"""서버 자동 시험.  실행: python -m pytest server/tests -q"""
from __future__ import annotations

import re
import sqlite3
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app

H = {"X-Requested-With": "ght"}


def make_settings(tmp_path, **over) -> Settings:
    base = dict(env="development", public_url="http://testserver", secret="test-secret", db_path=tmp_path / "t.db",
                session_days=30, sms_provider="console", solapi_key=None, solapi_secret=None, sms_from=None,
                kakao_rest_key=None, kakao_client_secret=None)
    base.update(over)
    return Settings(**base)


@pytest.fixture
def app(tmp_path):
    return create_app(make_settings(tmp_path))


@pytest.fixture
def client(app):
    return TestClient(app)


def last_code(app) -> str:
    to, text = app.state.sms.outbox[-1]
    return re.search(r"(\d{6})", text).group(1)


def db(app):
    conn = sqlite3.connect(app.state.settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def allow_resend(app, phone="010-1234-5678"):
    with db(app) as c:
        c.execute("UPDATE otp_codes SET created_at = '2000-01-01T00:00:00Z' WHERE phone = ?", (phone,))


def phone_signup(client, app, phone="01012345678", name="김순자"):
    assert client.post("/api/auth/phone/start", json={"phone": phone}, headers=H).status_code == 200
    r = client.post("/api/auth/phone/verify", json={"phone": phone, "code": last_code(app)}, headers=H)
    assert r.json()["status"] == "needs_profile"
    r = client.post("/api/auth/signup", headers=H, json={
        "name": name, "interests": ["혈압", "눈"], "channel": "sms", "time": "7",
        "agree_terms": True, "agree_privacy": True, "agree_health": True, "marketing": False})
    assert r.status_code == 200, r.text
    return r.json()["user"]


# ---------------------------------------------------------------- 기본 보안
def test_post_without_header_is_blocked(client):
    r = client.post("/api/auth/phone/start", json={"phone": "01012345678"})
    assert r.status_code == 403


def test_post_from_other_site_is_blocked(client):
    r = client.post("/api/auth/phone/start", json={"phone": "01012345678"},
                    headers={**H, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_pages_served_and_server_files_hidden(client):
    assert client.get("/").status_code == 200
    assert client.get("/my.html").status_code == 200
    assert client.get("/assets/css/site.css").status_code == 200
    for path in ("/server/config.py", "/server/.env", "/engine/README.md", "/README.md", "/server/data/app.db"):
        assert client.get(path).status_code == 404, path


def test_me_requires_login(client):
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "login_required"


# ---------------------------------------------------------------- 휴대폰
def test_phone_signup_login_logout(client, app):
    user = phone_signup(client, app)
    assert user["name"] == "김순자" and user["phone"] == "010-1234-5678" and user["channel"] == "sms"

    cookie = client.cookies.get("ght_session")
    set_cookie = client.get("/api/me").headers.get("set-cookie", "")  # 만료 연장이 없으면 비어 있을 수 있음
    assert cookie

    me = client.get("/api/me").json()["user"]
    assert me["interests"] == ["혈압", "눈"] and me["time"] == "7"

    assert len(client.get("/api/tips").json()["tips"]) == 21
    assert client.put("/api/me/saved/t02", headers=H).json()["ids"] == ["t02"]
    assert client.put("/api/me/saved/nope", headers=H).status_code == 404

    assert client.post("/api/auth/logout", headers=H).status_code == 200
    assert client.get("/api/me").status_code == 401

    allow_resend(app)
    client.post("/api/auth/phone/start", json={"phone": "010 1234 5678"}, headers=H)
    r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": last_code(app)}, headers=H)
    assert r.json()["status"] == "logged_in"
    assert client.get("/api/me/saved").json()["ids"] == ["t02"]   # 저장한 정보가 그대로 남아 있다


def test_session_cookie_is_httponly_and_lax(client, app):
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": last_code(app)}, headers=H)
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc


def test_code_is_not_stored_in_plain_text(client, app):
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    code = last_code(app)
    with db(app) as c:
        row = c.execute("SELECT code_hash FROM otp_codes").fetchone()
    assert code not in row["code_hash"]


def test_bad_phone(client):
    r = client.post("/api/auth/phone/start", json={"phone": "0212345678"}, headers=H)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_phone"


def test_resend_cooldown(client):
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    r = client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "cooldown"


def test_wrong_code_then_lockout(client, app):
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    good = last_code(app)
    bad = "000000" if good != "000000" else "111111"
    r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": bad}, headers=H)
    assert r.status_code == 400 and r.json()["detail"]["remaining"] == 4
    for _ in range(4):
        r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": bad}, headers=H)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "locked"
    # 잠긴 뒤에는 맞는 번호도 통하지 않는다
    r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": good}, headers=H)
    assert r.status_code == 429


def test_expired_code(client, app):
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    with db(app) as c:
        c.execute("UPDATE otp_codes SET expires_at = '2000-01-01T00:00:00Z'")
    r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": last_code(app)}, headers=H)
    assert r.status_code == 410


def test_code_works_once(client, app):
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    code = last_code(app)
    assert client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": code}, headers=H).status_code == 200
    r = client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": code}, headers=H)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_code"


def test_signup_needs_consent_and_pending(client, app):
    payload = {"name": "김순자", "interests": ["혈압"], "channel": "kakao", "time": "8",
               "agree_terms": True, "agree_privacy": True, "agree_health": False}
    assert client.post("/api/auth/signup", json=payload, headers=H).status_code == 401   # 본인 확인 전
    client.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    client.post("/api/auth/phone/verify", json={"phone": "01012345678", "code": last_code(app)}, headers=H)
    r = client.post("/api/auth/signup", json=payload, headers=H)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "consent_required"
    payload["agree_health"] = True
    payload["interests"] = ["없는값"]
    assert client.post("/api/auth/signup", json=payload, headers=H).status_code == 422


# ---------------------------------------------------------------- 카카오 (연습 화면)
def kakao_practice(client, nickname, next_page="my.html"):
    r = client.get(f"/api/auth/kakao/start?next={next_page}", follow_redirects=False)
    assert r.status_code == 302 and "/api/auth/kakao/practice" in r.headers["location"]
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    assert "동의하고 계속하기" in client.get(r.headers["location"]).text
    return client.post("/api/auth/kakao/practice", data={"state": state, "nickname": nickname}, follow_redirects=False), state


def test_kakao_signup_then_login(client):
    r, _ = kakao_practice(client, "박영희")
    assert r.status_code == 303 and r.headers["location"] == "/start.html?step=profile&next=my.html"
    p = client.get("/api/auth/pending").json()
    assert p["method"] == "kakao" and p["name_hint"] == "박영희"
    base = {"name": "박영희", "interests": ["특별히 없어요"], "time": "8",
            "agree_terms": True, "agree_privacy": True, "agree_health": True}
    r = client.post("/api/auth/signup", json={**base, "channel": "sms"}, headers=H)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "sms_needs_phone"
    user = client.post("/api/auth/signup", json={**base, "channel": "kakao"}, headers=H).json()["user"]
    assert user["method"] == "kakao" and user["phone"] is None

    client.post("/api/auth/logout", headers=H)
    r, _ = kakao_practice(client, "박영희", "membership.html")
    assert r.status_code == 303 and r.headers["location"] == "/membership.html"
    assert client.get("/api/me").json()["user"]["name"] == "박영희"


def test_kakao_state_cannot_be_reused(client):
    r, state = kakao_practice(client, "박영희")
    r2 = client.post("/api/auth/kakao/practice", data={"state": state, "nickname": "다른사람"}, follow_redirects=False)
    assert r2.headers["location"] == "/start.html?error=kakao_state"


def test_kakao_next_is_restricted(client):
    r = client.get("/api/auth/kakao/start?next=https://evil.example", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.post("/api/auth/kakao/practice", data={"state": state, "nickname": "누구"}, follow_redirects=False)
    assert r.headers["location"] == "/start.html?step=profile&next=my.html"


def test_kakao_real_mode_redirects_to_kakao(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, kakao_rest_key="REST_KEY")))
    r = c.get("/api/auth/kakao/start?next=my.html", follow_redirects=False)
    loc = r.headers["location"]
    assert loc.startswith("https://kauth.kakao.com/oauth/authorize?")
    q = parse_qs(urlparse(loc).query)
    assert q["client_id"] == ["REST_KEY"] and q["redirect_uri"] == ["http://testserver/api/auth/kakao/callback"]
    assert c.get("/api/auth/kakao/practice").status_code == 404   # 실제 키가 있으면 연습 화면은 닫힌다


# ---------------------------------------------------------------- 내 정보
def test_update_and_delete_me(client, app):
    phone_signup(client, app)
    r = client.patch("/api/me", json={"time": "9", "paused": True, "interests": ["관절·뼈"], "channel": "kakao"}, headers=H)
    u = r.json()["user"]
    assert (u["time"], u["paused"], u["interests"], u["channel"]) == ("9", True, ["관절·뼈"], "kakao")
    assert client.patch("/api/me", json={"time": "10"}, headers=H).status_code == 422
    client.put("/api/me/saved/t01", headers=H)

    assert client.delete("/api/me", headers=H).status_code == 200
    assert client.get("/api/me").status_code == 401
    with db(app) as c:
        assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM saved_tips").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM consents").fetchone()[0] == 0


def test_production_refuses_console_sms(tmp_path, monkeypatch):
    from server.config import ConfigError
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("PUBLIC_URL", "https://example.com")
    monkeypatch.setenv("SMS_PROVIDER", "console")
    with pytest.raises(ConfigError):
        Settings.load()


# ---------------------------------------------------------------- 로그인 여부 확인
def test_session_is_quiet_when_logged_out(client):
    r = client.get("/api/session")
    assert r.status_code == 200 and r.json() == {"user": None}


def test_session_returns_user_and_renews_cookie(client, app):
    phone_signup(client, app)
    assert client.get("/api/session").json()["user"]["name"] == "김순자"
    assert "set-cookie" not in client.get("/api/session").headers        # 막 로그인했으면 그대로 둔다
    with db(app) as c:                                                    # 29일이 지난 것처럼 만든다
        c.execute("UPDATE sessions SET expires_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+1 day')")
    r = client.get("/api/session")
    assert "max-age=2592000" in r.headers["set-cookie"].lower()
    with db(app) as c:
        assert c.execute("SELECT expires_at FROM sessions").fetchone()[0] > "2026"


def test_head_on_pages(client):
    assert client.head("/").status_code == 200


# ---------------------------------------------------------------- 실제 문자(솔라피) 연결 — 네트워크 없이 흉내
def solapi_app(tmp_path, monkeypatch, fail=None):
    import solapi
    sent = []

    def fake_send(self, message, request_config=None):
        if fail:
            raise fail
        sent.append((message.from_, message.to, message.text))

    monkeypatch.setattr(solapi.SolapiMessageService, "send", fake_send)
    app = create_app(make_settings(tmp_path, sms_provider="solapi", solapi_key="K", solapi_secret="S", sms_from="02-123-4567"))
    return app, sent


def test_solapi_sends_code_with_digits_only(tmp_path, monkeypatch):
    app, sent = solapi_app(tmp_path, monkeypatch)
    c = TestClient(app)
    r = c.post("/api/auth/phone/start", json={"phone": "010-1234-5678"}, headers=H)
    assert r.status_code == 200 and r.json()["console"] is False
    assert c.get("/api/config").json()["sms_console"] is False
    frm, to, text = sent[0]
    assert (frm, to) == ("021234567", "01012345678")
    assert re.search(r"인증번호 \d{6}", text)


def test_solapi_failure_is_reported_kindly(tmp_path, monkeypatch):
    app, _ = solapi_app(tmp_path, monkeypatch, fail=Exception("InvalidApiKey", "apiKey정보가 올바르지 않습니다"))
    c = TestClient(app)
    r = c.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "sms_failed"
    # 안 나간 문자는 기록에 남지 않아 바로 다시 시도할 수 있다 ('방금 보냈어요'로 막히지 않음)
    r = c.post("/api/auth/phone/start", json={"phone": "01012345678"}, headers=H)
    assert r.json()["detail"]["code"] == "sms_failed"
