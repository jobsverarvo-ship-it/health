"""카카오톡으로 보낼 메시지 글 만들기."""
from __future__ import annotations

from datetime import date

WEEKDAYS = "월화수목금토일"
NUMBERS = "①②③④⑤⑥⑦⑧⑨"


def format_message(day: date, tips: list[dict]) -> str:
    lines = [f"[하루온] {day.month}월 {day.day}일 {WEEKDAYS[day.weekday()]}요일 아침 건강 정보", ""]
    for i, t in enumerate(tips):
        head = f"{NUMBERS[i]} {t['title']}" if len(tips) > 1 else t["title"]
        lines.append(head)
        lines.append(t["body"])
        if t.get("action"):
            lines.append(f"👉 오늘 이렇게 해 보세요: {t['action']}")
        if t.get("caution"):
            lines.append(f"※ {t['caution']}")
        lines.append("")
    sources = []
    for t in tips:
        if t.get("source_name") and t["source_name"] not in sources:
            sources.append(t["source_name"])
    if sources:
        lines.append("출처: " + ", ".join(sources))
    lines.append("이 정보는 진단이나 치료를 대신하지 않아요. 몸이 갑자기 많이 아프면 119에 연락하세요.")
    return "\n".join(lines)
