"""식약처 DUR 노인주의 → 어르신이 특히 조심해야 하는 약 성분.

제품마다 줄이 따로 있어서, 성분 기준으로 하나로 모은다.
"""
from __future__ import annotations

from ..db import add_raw, get_state, set_state
from ..http import clean, extract_items, pick
from . import Ctx, fetch

CURSOR = "cursor:dur_elderly"


def collect(ctx: Ctx) -> int:
    page = int(get_state(ctx.conn, CURSOR, "1"))
    added = 0
    for _ in range(ctx.settings.pages_per_run):
        data = fetch(ctx, "dur_elderly", {"pageNo": page, "numOfRows": 100, "type": "json"})
        items = extract_items(data)
        if not items:
            page = 1
            break
        for it in items:
            ingr = clean(pick(it, "INGR_KOR_NAME", "INGR_NAME", "MAIN_INGR"))
            content = clean(pick(it, "PROHBT_CONTENT"))
            if not ingr or not content:
                continue
            code = pick(it, "INGR_CODE") or ingr
            payload = {
                "성분": ingr,
                "노인 주의 내용": content[:600],
                "전문/일반 의약품": clean(pick(it, "ETC_OTC_NAME")),
                "약 분류": clean(pick(it, "CLASS_NAME")),
                "참고 제품명": clean(pick(it, "ITEM_NAME")),
            }
            if add_raw(ctx.conn, source="dur_elderly", source_key=f"dur_elderly:{code}",
                       category="medicine_food", title=f"{ingr} (노인주의)", payload=payload,
                       source_name="식품의약품안전처 의약품안전사용서비스(DUR) 노인주의",
                       source_url="https://nedrug.mfds.go.kr"):
                added += 1
        page += 1
    set_state(ctx.conn, CURSOR, str(page))
    ctx.log(f"  DUR 노인주의: 새 성분 {added}건 (다음 페이지 {page})")
    return added
