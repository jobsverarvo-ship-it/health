"""날씨·미세먼지처럼 매일 바뀌는 정보는 미리 검토한 문장 틀에 숫자만 넣는다.

문장 틀은 출시 전에 약사가 한 번 검토해야 한다. 검토가 끝나면
AUTO_APPROVE_TEMPLATES=1 (기본) 로 두어 매일 자동 승인되게 한다.
"""
from __future__ import annotations

from datetime import date

from .db import add_tip


def temp_text(v: float) -> str:
    n = round(v)
    return f"영하 {abs(n)}도" if n < 0 else f"{n}도"


def _base(region: str, day: date, key: str, source: str, url: str) -> dict:
    d = day.isoformat()
    return {
        "dedupe_key": f"{key}:{region}:{d}",
        "category": "safety",
        "region": region,
        "valid_from": d,
        "valid_until": d,
        "kind": "live",
        "writer": "template",
        "source_name": source,
        "source_url": url,
    }


def weather_tip(region: str, day: date, tmn: float | None, tmx: float | None) -> dict | None:
    base = _base(region, day, "weather", "기상청 단기예보", "https://www.weather.go.kr")
    if tmx is not None and tmx >= 33:
        return {**base, "priority": 95, "tags": ["심장", "혈압"],
                "title": f"오늘 낮 최고 {temp_text(tmx)}, 더위를 조심하세요",
                "body": "나이가 들면 더위와 목마름을 덜 느끼고 땀도 덜 나서 열사병에 걸리기 쉬워요. "
                        "가장 더운 낮 12시부터 5시 사이에는 바깥일을 피하세요.",
                "action": "목이 마르지 않아도 물을 조금씩 자주 드시기",
                "caution": "물을 적게 드시라는 말을 들으신 분은 의사 지시를 따르세요."}
    if tmn is not None and tmn <= -10:
        return {**base, "priority": 95, "tags": ["혈압", "심장"],
                "title": f"오늘 아침 {temp_text(tmn)}, 한파를 조심하세요",
                "body": "기온이 갑자기 떨어지면 혈관이 좁아져 혈압이 오르기 쉬워요. "
                        "해 뜨기 전 이른 아침 외출과 새벽 운동은 오늘은 쉬세요.",
                "action": "나가실 땐 모자와 목도리로 머리와 목을 따뜻하게"}
    if tmn is not None and tmx is not None and tmx - tmn >= 12:
        diff = round(tmx - tmn)
        return {**base, "priority": 85, "tags": [],
                "title": f"오늘 일교차 {diff}도, 얇은 옷을 겹쳐 입으세요",
                "body": f"아침 {temp_text(tmn)}에서 낮 {temp_text(tmx)}까지 기온 차이가 커요. "
                        "큰 기온 변화는 몸에 부담이 되고 감기에 걸리기도 쉬워요.",
                "action": "벗고 입기 쉬운 얇은 옷을 여러 겹 입고 나가기"}
    if tmn is not None and tmn <= -3:
        return {**base, "priority": 80, "tags": ["혈압"],
                "title": f"오늘 아침 {temp_text(tmn)}, 욕실을 미리 데워 두세요",
                "body": "추운 방에서 따뜻한 욕실로 갑자기 들어가면 혈압이 크게 출렁여요. "
                        "겨울 아침에 씻을 때 특히 조심하세요.",
                "action": "샤워 전에 뜨거운 물을 1~2분 틀어 욕실 데우기"}
    return None


def air_grade(pm10: float | None, pm25: float | None) -> str | None:
    """환경부 예보 등급 기준. 두 값 중 더 나쁜 쪽."""
    level = 0
    if pm10 is not None:
        level = max(level, 3 if pm10 > 150 else 2 if pm10 > 80 else 1 if pm10 > 30 else 0)
    if pm25 is not None:
        level = max(level, 3 if pm25 > 75 else 2 if pm25 > 35 else 1 if pm25 > 15 else 0)
    return {2: "나쁨", 3: "매우 나쁨"}.get(level)


def air_tip(region: str, day: date, pm10: float | None, pm25: float | None) -> dict | None:
    grade = air_grade(pm10, pm25)
    if not grade:
        return None
    base = _base(region, day, "air", "에어코리아(한국환경공단) 실시간 측정", "https://www.airkorea.or.kr")
    return {**base, "priority": 95 if grade == "매우 나쁨" else 90, "tags": ["폐", "심장"],
            "title": f"오늘 미세먼지 '{grade}', 바깥 활동을 줄이세요",
            "body": "미세먼지는 숨길을 지나 심장과 폐에 부담을 줘요. "
                    "심장병이나 폐 질환이 있으시면 오늘은 특히 조심하세요.",
            "action": "외출할 땐 마스크를 쓰고, 돌아오면 손과 얼굴 씻기",
            "caution": "마스크를 쓰면 숨쉬기 힘든 분은 의사와 상의하세요."}


def save(ctx, tip: dict) -> bool:
    status = "approved" if ctx.settings.auto_approve_templates else "draft"
    return add_tip(ctx.conn, **tip, status=status) is not None
