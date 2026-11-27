"""문자 발송.

console : 개발용. 문자를 보내지 않고 서버 창(로그)에 내용을 찍는다.
solapi  : 솔라피(https://solapi.com) 실제 발송. 솔라피 공식 파이썬 라이브러리(solapi)를 쓴다.
          발신번호를 솔라피에 미리 등록해야 하고, 충전 잔액이 있어야 한다.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("ght.sms")


class SmsError(RuntimeError):
    pass


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


class ConsoleSms:
    def __init__(self):
        self.outbox: list[tuple[str, str]] = []   # 테스트에서 확인용

    def send(self, to: str, text: str) -> None:
        self.outbox.append((to, text))
        log.warning("[개발용 문자 · 실제로 보내지 않음] %s → %s", to, text)


class SolapiSms:
    def __init__(self, api_key: str, api_secret: str, sender: str):
        from solapi import SolapiMessageService   # 실제 발송을 켤 때만 필요
        self.service = SolapiMessageService(api_key=api_key, api_secret=api_secret)
        self.sender = digits(sender)

    def send(self, to: str, text: str) -> None:
        from solapi.model import RequestMessage
        try:
            self.service.send(RequestMessage(from_=self.sender, to=digits(to), text=text))
        except Exception as e:   # 키 오류, 잔액 부족, 미등록 발신번호, 네트워크 문제 등
            log.error("문자 발송 실패: %s", describe_error(e))
            raise SmsError("문자를 보내지 못했어요.") from e

    def balance(self) -> tuple[float | None, float | None]:
        """키가 맞는지 확인할 때 쓴다. (잔액, 포인트)"""
        r = self.service.get_balance()
        return r.balance, r.point


def describe_error(e: Exception) -> str:
    """솔라피 오류를 사람이 읽을 수 있게 정리한다."""
    failed = getattr(e, "failed_messages", None)
    if failed:
        return "; ".join(f"{m.status_code} {m.status_message}" for m in failed)
    if len(e.args) >= 2:
        return f"{e.args[0]} {e.args[1]}"
    return str(e) or e.__class__.__name__


def make_sender(settings):
    if settings.sms_provider == "solapi":
        return SolapiSms(settings.solapi_key, settings.solapi_secret, settings.sms_from)
    return ConsoleSms()
