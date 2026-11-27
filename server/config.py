"""서버 설정. server/.env 파일이나 환경 변수에서 읽는다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # 사이트 폴더 (index.html 이 있는 곳)
SERVER_DIR = ROOT / "server"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    env: str
    public_url: str
    secret: str
    db_path: Path
    session_days: int
    sms_provider: str           # console | solapi
    solapi_key: str | None
    solapi_secret: str | None
    sms_from: str | None
    kakao_rest_key: str | None
    kakao_client_secret: str | None

    @property
    def dev(self) -> bool:
        return self.env == "development"

    @property
    def cookie_secure(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def kakao_enabled(self) -> bool:
        return bool(self.kakao_rest_key)

    @property
    def kakao_redirect_uri(self) -> str:
        return self.public_url.rstrip("/") + "/api/auth/kakao/callback"

    @classmethod
    def load(cls) -> "Settings":
        _load_dotenv(SERVER_DIR / ".env")
        env = os.environ.get("APP_ENV", "development")
        secret = os.environ.get("APP_SECRET", "")
        if not secret:
            if env != "development":
                raise ConfigError("APP_SECRET 이 없어요. 운영 환경에서는 길고 무작위한 값을 꼭 넣어야 해요.")
            secret = "dev-only-secret-change-me"
        sms_provider = os.environ.get("SMS_PROVIDER", "console")
        s = cls(
            env=env,
            public_url=os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/"),
            secret=secret,
            db_path=Path(os.environ.get("DB_PATH", SERVER_DIR / "data" / "app.db")),
            session_days=int(os.environ.get("SESSION_DAYS", "30")),
            sms_provider=sms_provider,
            solapi_key=os.environ.get("SOLAPI_API_KEY") or None,
            solapi_secret=os.environ.get("SOLAPI_API_SECRET") or None,
            sms_from=os.environ.get("SMS_FROM") or None,
            kakao_rest_key=os.environ.get("KAKAO_REST_API_KEY") or None,
            kakao_client_secret=os.environ.get("KAKAO_CLIENT_SECRET") or None,
        )
        if not s.dev:
            # 운영에서 인증번호를 화면(로그)에만 찍는 일이 없도록 막는다
            if s.sms_provider == "console":
                raise ConfigError("운영 환경에서는 SMS_PROVIDER=solapi 로 실제 문자 발송을 설정해야 해요.")
            if not s.cookie_secure:
                raise ConfigError("운영 환경의 PUBLIC_URL 은 https:// 로 시작해야 해요.")
        if s.sms_provider == "solapi" and not (s.solapi_key and s.solapi_secret and s.sms_from):
            raise ConfigError("SOLAPI_API_KEY, SOLAPI_API_SECRET, SMS_FROM(사전 등록한 발신번호)을 모두 넣어 주세요.")
        return s
