"""기상청 단기예보 → 지역별 '오늘의 날씨 건강 정보'."""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import templates
from ..config import KST, REGIONS, now_kst
from ..http import extract_items, pick
from . import Ctx, active_regions, fetch

BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]


def base_for(day, now: datetime) -> tuple[str, str]:
    """그날 최저(TMN)·최고(TMX) 기온이 들어 있는 가장 최근 발표 시각을 고른다.

    오늘 최저기온(06시)은 02시·05시 발표에만 들어 있어서, 오늘 것은 02시 발표를 쓴다.
    발표 후 API에 올라오기까지 10분 정도 걸리므로 15분 여유를 둔다.
    """
    today = now.date()
    if day <= today:
        if now.hour > 2 or (now.hour == 2 and now.minute >= 15):
            return today.strftime("%Y%m%d"), "0200"
        y = today - timedelta(days=1)
        return y.strftime("%Y%m%d"), "2300"
    # 내일 이후 날짜는 지금 나와 있는 가장 최근 발표를 쓴다
    ready = now - timedelta(minutes=15)
    for bt in reversed(BASE_TIMES):
        t = datetime.combine(today, datetime.strptime(bt, "%H%M").time(), KST)
        if t <= ready:
            return today.strftime("%Y%m%d"), bt
    y = today - timedelta(days=1)
    return y.strftime("%Y%m%d"), "2300"


def collect(ctx: Ctx) -> int:
    regions = ctx.regions or active_regions(ctx.conn)
    if not regions:
        ctx.log("  날씨: 받는 분의 지역 정보가 없어서 건너뜀")
        return 0
    base_date, base_time = base_for(ctx.day, now_kst())
    target = ctx.day.strftime("%Y%m%d")
    added = 0
    for region in regions:
        g = REGIONS[region]
        data = fetch(
            ctx, "weather",
            {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
             "base_date": base_date, "base_time": base_time, "nx": g["nx"], "ny": g["ny"]},
            sample_key=f"{g['nx']},{g['ny']}",
        )
        tmn = tmx = None
        for it in extract_items(data):
            if pick(it, "fcstDate") != target:
                continue
            cat = pick(it, "category")
            try:
                value = float(pick(it, "fcstValue"))
            except ValueError:
                continue
            if cat == "TMN":
                tmn = value
            elif cat == "TMX":
                tmx = value
        tip = templates.weather_tip(region, ctx.day, tmn, tmx)
        ctx.log(f"  날씨 {region}: 최저 {tmn} / 최고 {tmx} → {tip['title'] if tip else '알릴 것 없음'}")
        if tip and templates.save(ctx, tip):
            added += 1
    return added
