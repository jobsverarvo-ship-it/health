"""설정: 환경 변수(.env)와 API 주소, 지역, 분류 같은 고정 값."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어서 고정 +9시간
ENGINE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ENGINE_DIR / "samples"


def _load_dotenv(path: Path) -> None:
    """engine/.env 파일이 있으면 읽어서 환경 변수로 넣는다 (이미 있는 값은 덮어쓰지 않음)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ENGINE_DIR / ".env")


# ---------------------------------------------------------------------------
# 공공데이터 API 주소
# 포털 화면에 경로 이름이 나오지 않는 것도 있어서, 틀리면 .env 에서
# ENDPOINT_<이름>=주소 로 바꿀 수 있게 했다.
# ---------------------------------------------------------------------------
DEFAULT_ENDPOINTS = {
    # 기상청_단기예보 조회서비스 (data.go.kr 15084084)
    "weather": "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
    # 한국환경공단_에어코리아_대기오염정보 > 시도별 실시간 측정정보 (15073861)
    "air": "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty",
    # 식품의약품안전처_의약품개요정보(e약은요) (15075057)
    "drug_easy": "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList",
    # 식품의약품안전처_의약품안전사용서비스(DUR)품목정보 > 노인주의 (15059486)
    "dur_elderly": "https://apis.data.go.kr/1471000/DURPrdlstInfoService03/getOdsnAtentInfoList03",
    # 행정안전부_대한민국 공공서비스(혜택) 정보 > serviceList (15113968)
    "gov24": "https://api.odcloud.kr/api/gov24/v3/serviceList",
}


def endpoint(name: str) -> str:
    return os.environ.get(f"ENDPOINT_{name.upper()}", DEFAULT_ENDPOINTS[name])


# ---------------------------------------------------------------------------
# 지역: 날씨(기상청 격자 nx, ny)와 미세먼지(에어코리아 sidoName)에 쓴다.
# 격자 값은 각 지역 대표 지점이다. 정확한 값은 기상청 API 활용가이드의
# 격자 위경도 엑셀로 한 번 확인할 것.
# ---------------------------------------------------------------------------
REGIONS = {
    "서울": {"nx": 60, "ny": 127, "sido": "서울"},
    "부산": {"nx": 98, "ny": 76, "sido": "부산"},
    "대구": {"nx": 89, "ny": 90, "sido": "대구"},
    "인천": {"nx": 55, "ny": 124, "sido": "인천"},
    "광주": {"nx": 58, "ny": 74, "sido": "광주"},
    "대전": {"nx": 67, "ny": 100, "sido": "대전"},
    "울산": {"nx": 102, "ny": 84, "sido": "울산"},
    "세종": {"nx": 66, "ny": 103, "sido": "세종"},
    "경기": {"nx": 60, "ny": 121, "sido": "경기"},  # 수원
    "제주": {"nx": 52, "ny": 38, "sido": "제주"},
}

# ---------------------------------------------------------------------------
# 분류 (사이트의 6가지 주제와 같다)
# ---------------------------------------------------------------------------
CATEGORIES = {
    "medicine_food": "약과 음식 궁합",
    "supplement": "영양제 제대로 먹기",
    "body_signal": "몸이 보내는 신호",
    "safety": "생활 속 사고 예방",
    "benefit": "나라에서 주는 혜택",
    "brain_sense": "뇌와 감각 건강",
}

# 요일별 중심 주제 (월=0 ... 일=6). 그날 이 주제가 조금 더 우선된다.
WEEKDAY_THEME = [
    "medicine_food",
    "supplement",
    "body_signal",
    "safety",
    "benefit",
    "brain_sense",
    "supplement",
]

# 관심 건강 태그. 받는 분이 고른 관심사와 겹치면 우선 보낸다.
TAGS = [
    "혈압", "당뇨", "관절", "심장", "폐", "뼈", "수면", "소화",
    "눈", "귀", "기억력", "피부", "신장", "간",
]


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    data_go_kr_key: str | None
    db_path: Path
    outbox_dir: Path
    writer: str            # auto | ai | rule
    model: str
    effort: str
    tips_free: int         # 무료 회원 하루 정보 개수
    tips_member: int       # 멤버십 회원 하루 정보 개수
    pages_per_run: int     # 자료원별로 한 번에 가져올 페이지 수
    max_drafts_per_run: int
    auto_approve_templates: bool

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("HARUON_DATA_DIR", ENGINE_DIR / "data"))
        return cls(
            data_go_kr_key=os.environ.get("DATA_GO_KR_KEY") or None,
            db_path=data_dir / "haruon.db",
            outbox_dir=data_dir / "outbox",
            writer=os.environ.get("HARUON_WRITER", "auto"),
            model=os.environ.get("HARUON_MODEL", "claude-opus-5-5"),
            effort=os.environ.get("HARUON_EFFORT", "medium"),
            tips_free=_int("TIPS_PER_DAY_FREE", 1),
            tips_member=_int("TIPS_PER_DAY_MEMBER", 3),
            pages_per_run=_int("PAGES_PER_RUN", 1),
            max_drafts_per_run=_int("MAX_DRAFTS_PER_RUN", 10),
            auto_approve_templates=os.environ.get("AUTO_APPROVE_TEMPLATES", "1") == "1",
        )


def now_kst() -> datetime:
    return datetime.now(KST)
