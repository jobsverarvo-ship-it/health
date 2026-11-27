"""원본 자료 → 어르신용 건강 정보 초안.

AI(Claude API)가 쉬운 말로 다시 쓰고, 금지 표현 검사를 거쳐 'draft' 로 저장한다.
발송은 약사가 승인한 것만 된다.

HARUON_WRITER
  auto (기본): anthropic 패키지와 인증 정보가 있으면 AI, 없으면 규칙 초안
  ai         : 항상 AI (실패하면 오류)
  rule       : AI 없이 원문을 잘라 붙인 초안 (약사가 직접 다듬어야 함)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3

from .config import CATEGORIES, TAGS, Settings
from .db import add_tip

SYSTEM_PROMPT = """당신은 60세 이상 어르신에게 매일 아침 카카오톡으로 건강 정보를 보내는 서비스 '하루온'의 콘텐츠 작가입니다.
공공기관 자료(원문)를 받아, 어르신이 한 번 읽고 이해해서 오늘 바로 해 볼 수 있는 건강 정보 한 건으로 다시 씁니다.
쓴 글은 약사가 검토한 뒤에만 발송됩니다.

지켜야 할 것
- 원문에 있는 사실만 씁니다. 원문에 없는 효능, 수치, 연구 결과를 만들어 내지 않습니다.
- 병을 진단하거나, 약을 먹으라/끊으라/바꾸라고 하지 않습니다. 약 이야기는 "드시는 약이 있으면 약사나 의사와 상의하세요" 방향으로 맺습니다.
- '치료', '완치', '낫는다', '특효', '예방된다'처럼 효과를 단정하는 표현을 쓰지 않습니다.
- 제품명(상표)과 회사명을 쓰지 않습니다. 성분명이나 '일부 진통제·감기약'처럼 일반적인 이름으로 씁니다.
- 해요체 존댓말, 짧은 문장, 쉬운 말로 씁니다. 영어와 전문 용어는 풀어서 씁니다.
- '물 많이 드세요', '골고루 드세요', '하루 30분 걸으세요'처럼 누구나 아는 이야기는 쓰지 않습니다.
- 지원 제도는 누가, 무엇을, 어디서 신청하는지가 드러나게 씁니다.
- 어르신에게 쓸모가 적거나, 원문만으로는 정확하게 쓰기 어려우면 usable 을 false 로 하고 reason 에 이유를 적습니다.

형식
- title: 30자 안쪽. 오늘 알아 두실 핵심 한 줄.
- body: 2~3문장, 120자 안쪽. 왜 중요한지.
- action: 40자 안쪽. "오늘 이렇게 해 보세요" 에 들어갈 행동 한 가지.
- caution: 꼭 필요할 때만 60자 안쪽 (예: 약을 드시는 분은 약사와 상의). 없으면 빈 문자열.
- tags: 아래 목록에서 관련 있는 것만 고릅니다. 없으면 빈 목록.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {"type": "boolean"},
        "reason": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "action": {"type": "string"},
        "caution": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string", "enum": TAGS}},
    },
    "required": ["usable", "reason", "title", "body", "action", "caution", "tags"],
    "additionalProperties": False,
}

# 효과를 단정하거나 진단·처방처럼 읽히는 표현
BANNED = [
    "완치", "치료됩", "치료해", "치료할 수", "낫습니다", "낫는다", "나아집니다", "특효",
    "예방됩니다", "예방된다", "예방할 수 있습니다", "효과가 뛰어", "100%", "반드시 좋아",
    "진단", "처방해", "끊으세요", "중단하세요",
]
LIMITS = {"title": 34, "body": 140, "action": 46, "caution": 70}


class WriterUnavailable(Exception):
    pass


def lint(draft: dict, payload: dict) -> list[str]:
    """검토자가 꼭 봐야 할 점을 찾아 경고로 남긴다."""
    flags = []
    text = " ".join(draft.get(k, "") for k in ("title", "body", "action", "caution"))
    for word in BANNED:
        if word in text:
            flags.append(f"금지 표현 의심: '{word}'")
    for key, limit in LIMITS.items():
        if len(draft.get(key, "")) > limit:
            flags.append(f"{key} 가 깁니다 ({len(draft[key])}자)")
    product = str(payload.get("제품명") or payload.get("참고 제품명") or "")
    base_name = re.sub(r"\(.*?\)", "", product).strip()
    if len(base_name) >= 2 and base_name in text:
        flags.append(f"제품명이 들어 있음: '{base_name}'")
    return flags


class Writer:
    def __init__(self, settings: Settings, log=print):
        self.settings = settings
        self.log = log
        self.mode = settings.writer
        self._client = None
        if self.mode == "auto" and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            self.log("  (ANTHROPIC_API_KEY 가 없어서 AI 없이 규칙 초안으로 씁니다)")
            self.mode = "rule"
        if self.mode in ("auto", "ai"):
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except Exception as e:  # 패키지가 없거나 인증 정보를 못 찾음
                if self.mode == "ai":
                    raise WriterUnavailable(f"Claude API를 쓸 수 없어요: {e}") from e
                self.log(f"  (AI 없이 규칙 초안으로 씁니다: {e})")
                self.mode = "rule"
            else:
                self.mode = "ai"

    # -- AI ----------------------------------------------------------------
    def _ai(self, category: str, source_name: str, payload: dict) -> dict:
        import anthropic

        content = (f"분류: {CATEGORIES[category]}\n출처: {source_name}\n\n"
                   f"원문(JSON):\n{json.dumps(payload, ensure_ascii=False, indent=1)}")
        try:
            resp = self._client.beta.messages.create(
                model=self.settings.model,
                max_tokens=8000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": self.settings.effort,
                               "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": content}],
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise WriterUnavailable(f"Claude API 인증 실패: {e}") from e
        if resp.stop_reason == "refusal":
            return {"usable": False, "reason": "AI가 이 자료로 글쓰기를 거절했어요"}
        if resp.stop_reason == "max_tokens":
            return {"usable": False, "reason": "AI 답이 길이 제한에 걸렸어요"}
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)

    # -- 규칙 초안 (AI가 없을 때) ---------------------------------------------
    @staticmethod
    def _rule(category: str, title: str, payload: dict) -> dict:
        main = ""
        for key in ("이 약을 쓰는 동안 주의할 약 또는 음식", "노인 주의 내용", "서비스목적요약", "지원내용"):
            if payload.get(key):
                main = payload[key]
                break
        how = payload.get("신청방법", "")
        return {
            "usable": True, "reason": "",
            "title": f"[다듬기 필요] {title}"[:34],
            "body": main[:140],
            "action": (f"신청: {how}" if how else "드시는 약이 있으면 약사와 상의하세요")[:46],
            "caution": "",
            "tags": [],
        }

    def draft(self, raw: sqlite3.Row) -> dict:
        payload = json.loads(raw["payload"])
        if self.mode == "ai":
            return self._ai(raw["category"], raw["source_name"], payload) | {"writer": "ai"}
        return self._rule(raw["category"], raw["title"], payload) | {"writer": "rule"}


def draft_pending(conn: sqlite3.Connection, settings: Settings, limit: int | None = None, log=print) -> dict:
    """새로 모인 원본 자료로 초안을 만든다."""
    limit = limit or settings.max_drafts_per_run
    rows = conn.execute(
        "SELECT * FROM raw_items WHERE status = 'new' ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    if not rows:
        return {"drafted": 0, "skipped": 0, "mode": "-"}
    writer = Writer(settings, log=log)
    drafted = skipped = 0
    for raw in rows:
        payload = json.loads(raw["payload"])
        try:
            try:
                d = writer.draft(raw)
            except WriterUnavailable:
                if settings.writer != "auto":
                    raise
                log("  (Claude API 인증에 실패해서 남은 자료는 규칙 초안으로 씁니다)")
                writer.mode = "rule"
                d = writer.draft(raw)
        except WriterUnavailable:
            raise
        except Exception as e:  # 한 건이 실패해도 나머지는 계속
            conn.execute("UPDATE raw_items SET note = ? WHERE id = ?", (f"초안 실패: {e}", raw["id"]))
            log(f"  #{raw['id']} 초안 실패: {e}")
            continue
        if not d.get("usable"):
            conn.execute("UPDATE raw_items SET status = 'skipped', note = ? WHERE id = ?",
                         (d.get("reason", ""), raw["id"]))
            skipped += 1
            log(f"  #{raw['id']} 건너뜀: {d.get('reason', '')}")
            continue
        flags = lint(d, payload)
        if d["writer"] == "rule":
            flags.insert(0, "AI 없이 만든 초안이에요. 문장을 직접 다듬어 주세요.")
        tags = [t for t in d.get("tags", []) if t in TAGS]
        tip_id = add_tip(
            conn, raw_id=raw["id"], dedupe_key=f"raw:{raw['id']}", category=raw["category"],
            title=d["title"].strip(), body=d["body"].strip(), action=d["action"].strip(),
            caution=d.get("caution", "").strip(), source_name=raw["source_name"],
            source_url=raw["source_url"], tags=tags, writer=d["writer"], flags=flags,
            priority=60 if raw["category"] == "benefit" else 50,
        )
        conn.execute("UPDATE raw_items SET status = 'drafted' WHERE id = ?", (raw["id"],))
        conn.commit()
        drafted += 1
        warn = f" ⚠ {len(flags)}" if flags else ""
        log(f"  #{raw['id']} → 초안 #{tip_id}: {d['title']}{warn}")
    conn.commit()
    return {"drafted": drafted, "skipped": skipped, "mode": writer.mode}
