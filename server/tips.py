"""건강정보함에 보여 줄 정보.

지금은 사이트의 assets/js/tips-data.js 를 그대로 읽어 오늘부터 하루씩 거슬러 날짜를 붙인다.
콘텐츠 엔진(engine 폴더)과 연결하면, 엔진이 실제로 보낸 정보와 날짜를 여기서 돌려주면 된다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))


def load(root: Path) -> list[dict]:
    text = (root / "assets" / "js" / "tips-data.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("["): text.rindex("]") + 1])


def with_dates(tips: list[dict]) -> list[dict]:
    today = datetime.now(KST).date()
    return [{**t, "date": (today - timedelta(days=i)).isoformat()} for i, t in enumerate(tips)]
