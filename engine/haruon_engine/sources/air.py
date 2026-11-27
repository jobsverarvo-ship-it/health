"""에어코리아 시도별 실시간 측정 → 미세먼지가 나쁜 날 정보."""
from __future__ import annotations

from .. import templates
from ..config import REGIONS, now_kst
from ..http import extract_items, pick
from . import Ctx, active_regions, fetch


def _avg(values: list[str]) -> float | None:
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except ValueError:
            continue  # 점검 중인 측정소는 "-" 로 온다
    return sum(nums) / len(nums) if nums else None


def collect(ctx: Ctx) -> int:
    if ctx.day != now_kst().date() and not ctx.sample:
        ctx.log("  미세먼지: 실시간 자료라 오늘 날짜에만 씀, 건너뜀")
        return 0
    regions = ctx.regions or active_regions(ctx.conn)
    added = 0
    for region in regions:
        sido = REGIONS[region]["sido"]
        data = fetch(
            ctx, "air",
            {"sidoName": sido, "returnType": "json", "numOfRows": 200, "pageNo": 1, "ver": "1.0"},
            sample_key=sido,
        )
        items = extract_items(data)
        pm10 = _avg([pick(it, "pm10Value") for it in items])
        pm25 = _avg([pick(it, "pm25Value") for it in items])
        tip = templates.air_tip(region, ctx.day, pm10, pm25)
        shown = f"{pm10:.0f}/{pm25:.0f}" if pm10 is not None and pm25 is not None else "자료 없음"
        ctx.log(f"  미세먼지 {region}: PM10/PM2.5 평균 {shown} → {tip['title'] if tip else '알릴 것 없음'}")
        if tip and templates.save(ctx, tip):
            added += 1
    return added
