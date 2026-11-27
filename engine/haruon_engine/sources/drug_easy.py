"""식약처 e약은요 → '이 약을 먹는 동안 조심할 음식' 이 있는 자료만 모은다.

전체 일반의약품을 한 번에 다 받지 않고, 실행할 때마다 다음 페이지를 조금씩 읽는다.
같은 주의 문구를 쓰는 제품이 많아서 문구 기준으로 중복을 없앤다.
"""
from __future__ import annotations

import hashlib

from ..db import add_raw, get_state, set_state
from ..http import clean, extract_items, pick
from . import Ctx, fetch

FOOD_WORDS = ("술", "음주", "알코올", "알콜", "우유", "유제품", "자몽", "카페인",
              "커피", "녹차", "홍차", "주스", "음식")
CURSOR = "cursor:drug_easy"


def collect(ctx: Ctx) -> int:
    page = int(get_state(ctx.conn, CURSOR, "1"))
    added = 0
    for _ in range(ctx.settings.pages_per_run):
        data = fetch(ctx, "drug_easy", {"pageNo": page, "numOfRows": 100, "type": "json"})
        items = extract_items(data)
        if not items:
            page = 1  # 끝까지 읽었으면 처음부터 (새로 추가·수정된 제품을 다시 보기 위해)
            break
        for it in items:
            intrc = clean(pick(it, "intrcQesitm"))
            if not intrc or not any(w in intrc for w in FOOD_WORDS):
                continue
            digest = hashlib.sha1(intrc.encode("utf-8")).hexdigest()[:16]
            payload = {
                "제품명": clean(pick(it, "itemName")),
                "효능": clean(pick(it, "efcyQesitm"))[:400],
                "이 약을 쓰는 동안 주의할 약 또는 음식": intrc[:800],
                "사용상 주의사항": clean(pick(it, "atpnQesitm"))[:600],
            }
            if add_raw(ctx.conn, source="drug_easy", source_key=f"drug_easy:{digest}",
                       category="medicine_food", title=payload["제품명"], payload=payload,
                       source_name="식품의약품안전처 의약품개요정보(e약은요)",
                       source_url="https://nedrug.mfds.go.kr"):
                added += 1
        page += 1
    set_state(ctx.conn, CURSOR, str(page))
    ctx.log(f"  e약은요: 새 자료 {added}건 (다음 페이지 {page})")
    return added
