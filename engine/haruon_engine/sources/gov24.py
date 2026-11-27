"""행안부 공공서비스(보조금24) → 어르신 대상 지원 제도."""
from __future__ import annotations

from ..db import add_raw, get_state, set_state
from ..http import clean
from . import Ctx, fetch

SENIOR_WORDS = ("노인", "어르신", "고령", "65세", "60세", "만65", "만 65", "만60", "만 60",
                "기초연금", "장기요양", "치매", "경로당", "경로")
FIELDS = ("서비스명", "서비스목적요약", "지원대상", "선정기준", "지원내용",
          "신청방법", "신청기한", "소관기관명", "전화문의")
CURSOR = "cursor:gov24"


def collect(ctx: Ctx) -> int:
    page = int(get_state(ctx.conn, CURSOR, "1"))
    added = 0
    for _ in range(ctx.settings.pages_per_run * 3):  # 한 페이지에 어르신 대상이 적어서 조금 더 읽는다
        data = fetch(ctx, "gov24", {"page": page, "perPage": 100, "returnType": "JSON",
                                    "cond[사용자구분::LIKE]": "개인"})
        items = data.get("data") or [] if isinstance(data, dict) else []
        if not items:
            page = 1
            break
        for it in items:
            text = " ".join(str(it.get(k, "")) for k in ("서비스명", "지원대상", "서비스목적요약"))
            if not any(w in text for w in SENIOR_WORDS):
                continue
            sid = str(it.get("서비스ID", "")).strip()
            if not sid:
                continue
            payload = {k: clean(str(it.get(k, "")))[:500] for k in FIELDS if it.get(k)}
            if add_raw(ctx.conn, source="gov24", source_key=f"gov24:{sid}", category="benefit",
                       title=payload.get("서비스명", sid), payload=payload,
                       source_name=f"정부24 공공서비스 ({payload.get('소관기관명', '행정안전부')})",
                       source_url=str(it.get("상세조회URL") or "https://www.gov.kr")):
                added += 1
        page += 1
    set_state(ctx.conn, CURSOR, str(page))
    ctx.log(f"  정부24 혜택: 새 자료 {added}건 (다음 페이지 {page})")
    return added
