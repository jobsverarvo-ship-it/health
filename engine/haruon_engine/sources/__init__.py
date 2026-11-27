"""자료원(공공데이터 API) 모음.

- 실시간 자료원(weather, air): 그날 그 지역에만 맞는 정보를 미리 검토된 문장 틀로 바로 만든다.
- 원본 자료원(drug_easy, dur_elderly, gov24): 원문을 raw_items 에 쌓고, 나중에 AI가 초안을 쓴다.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from ..config import SAMPLES_DIR, Settings, endpoint
from ..http import ApiError, get_json

# 각 API 문서에 적힌 인증키 파라미터 이름
KEY_PARAM = {
    "weather": "ServiceKey",
    "air": "serviceKey",
    "drug_easy": "ServiceKey",
    "dur_elderly": "serviceKey",
    "gov24": "serviceKey",
}


@dataclass
class Ctx:
    conn: sqlite3.Connection
    settings: Settings
    day: date
    sample: bool = False
    log: Callable[[str], None] = print
    regions: list[str] = field(default_factory=list)


def fetch(ctx: Ctx, name: str, params: dict, sample_key: str | None = None):
    """API를 부른다. sample 모드면 samples/<name>.json 을 대신 읽는다."""
    if ctx.sample:
        return load_sample(name, sample_key, ctx.day)
    key = ctx.settings.data_go_kr_key
    if not key:
        raise ApiError("DATA_GO_KR_KEY 가 없어요. engine/.env 에 공공데이터포털 인증키를 넣거나 --sample 로 실행하세요.")
    return get_json(endpoint(name), {**params, KEY_PARAM[name]: key})


def load_sample(name: str, sample_key: str | None, day: date):
    path = SAMPLES_DIR / f"{name}.json"
    text = path.read_text(encoding="utf-8")
    text = text.replace("{TODAY}", day.strftime("%Y%m%d")).replace(
        "{YESTERDAY}", (day - timedelta(days=1)).strftime("%Y%m%d"))
    data = json.loads(text)
    data.pop("_note", None)
    if sample_key is not None:
        return data.get(sample_key, {"response": {"body": {"items": []}}})
    return data


def active_regions(conn: sqlite3.Connection) -> list[str]:
    from ..config import REGIONS
    rows = conn.execute("SELECT DISTINCT region FROM users WHERE active = 1 AND region IS NOT NULL").fetchall()
    return [r["region"] for r in rows if r["region"] in REGIONS]


def run_all(ctx: Ctx, only: str | None = None) -> dict[str, str]:
    """모든 자료원을 돌린다. 한 곳이 실패해도 나머지는 계속한다."""
    from . import air, drug_easy, dur, gov24, weather

    jobs = {
        "weather": weather.collect,
        "air": air.collect,
        "drug_easy": drug_easy.collect,
        "dur_elderly": dur.collect,
        "gov24": gov24.collect,
    }
    results: dict[str, str] = {}
    for name, job in jobs.items():
        if only and name != only:
            continue
        try:
            n = job(ctx)
            results[name] = f"새 자료 {n}건"
        except ApiError as e:
            results[name] = f"실패: {e}"
        ctx.conn.commit()
    return results
