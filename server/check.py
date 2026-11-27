"""키 확인 도구.  server/.env 에 넣은 키가 제대로 됐는지 사이트를 켜기 전에 확인한다.

    python -m server.check                    설정과 키 확인 (문자는 보내지 않음)
    python -m server.check --send 01012345678  그 번호로 시험 문자 한 통 보내기 (요금이 나감)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from .config import SERVER_DIR, ConfigError, Settings

OK, NO, INFO = "[통과]", "[확인 필요]", "[안내]"

KAKAO_HINTS = {
    "KOE101": "REST API 키가 틀렸어요. [앱] > [플랫폼 키] > [REST API 키] 값을 다시 복사해 넣으세요.",
    "KOE010": "클라이언트 시크릿이 없거나 틀렸어요. [앱] > [플랫폼 키] > [REST API 키] > [클라이언트 시크릿] 값을 "
              "KAKAO_CLIENT_SECRET 에 넣으세요.",
}


def mask(v: str | None) -> str:
    if not v:
        return "(비어 있음)"
    return v[:4] + "…" + f"({len(v)}자)"


def check_kakao(s: Settings) -> bool:
    """가짜 인가 코드로 토큰을 요청해 본다. 키·시크릿이 맞으면 '코드가 틀렸다(invalid_grant)'는 답이 온다."""
    print("\n■ 카카오 로그인")
    if not s.kakao_enabled:
        print(f"  {INFO} KAKAO_REST_API_KEY 가 비어 있어요. 지금은 연습 화면이 열려요.")
        return True
    print(f"  REST API 키: {mask(s.kakao_rest_key)}")
    print(f"  클라이언트 시크릿: {mask(s.kakao_client_secret)}")
    form = {"grant_type": "authorization_code", "client_id": s.kakao_rest_key,
            "redirect_uri": s.kakao_redirect_uri, "code": "key-check-only"}
    if s.kakao_client_secret:
        form["client_secret"] = s.kakao_client_secret
    req = urllib.request.Request("https://kauth.kakao.com/oauth/token", data=urllib.parse.urlencode(form).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8"))
        except ValueError:
            data = {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        print(f"  {NO} 카카오에 연결하지 못했어요: {e.reason}")
        return False
    if data.get("error") == "invalid_grant":
        print(f"  {OK} 카카오가 앱 키{'와 클라이언트 시크릿' if s.kakao_client_secret else ''}을 알아봤어요.")
        print(f"  {INFO} 카카오 콘솔에 아래 리다이렉트 URI를 글자 하나 틀리지 않게 등록해 두세요.\n"
              f"         {s.kakao_redirect_uri}\n"
              "         (등록이 맞는지는 사이트에서 '카카오로 시작하기'를 한 번 해 보면 확인돼요.)")
        return True
    code = data.get("error_code", "")
    print(f"  {NO} 카카오 오류 {code or data.get('error')}: {data.get('error_description', '')}")
    if code in KAKAO_HINTS:
        print(f"         {KAKAO_HINTS[code]}")
    return False


def check_sms(s: Settings, send_to: str | None) -> bool:
    print("\n■ 문자 인증")
    if s.sms_provider != "solapi":
        print(f"  {INFO} SMS_PROVIDER={s.sms_provider}. 문자를 실제로 보내지 않고 서버 창에 인증번호가 찍혀요.")
        if send_to:
            print(f"  {NO} 시험 문자를 보내려면 SMS_PROVIDER=solapi 로 바꾸세요.")
            return False
        return True
    from .sms import SmsError, SolapiSms, describe_error, digits
    print(f"  API 키: {mask(s.solapi_key)}   발신번호: {s.sms_from}")
    try:
        sender = SolapiSms(s.solapi_key, s.solapi_secret, s.sms_from)
    except ImportError:
        print(f"  {NO} 솔라피 라이브러리가 없어요.  pip install -r server/requirements.txt  를 먼저 실행하세요.")
        return False
    try:
        balance, point = sender.balance()
        print(f"  {OK} 솔라피 키가 맞아요. 잔액 {balance or 0:,.0f}원, 포인트 {point or 0:,.0f}")
        if not (balance or point):
            print(f"  {NO} 잔액이 없어요. 솔라피에서 충전해야 문자가 나가요.")
    except Exception as e:
        print(f"  {NO} 솔라피 키 확인 실패: {describe_error(e)}")
        print("         API 키와 시크릿을 다시 복사해 넣었는지 확인하세요.")
        return False
    if send_to:
        to = digits(send_to)
        try:
            sender.send(to, "[건강한통] 시험 문자예요. 이 문자가 오면 문자 인증 준비가 끝났어요.")
            print(f"  {OK} {to} 로 시험 문자를 보냈어요. 휴대폰을 확인해 보세요.")
        except SmsError as e:
            print(f"  {NO} 시험 문자를 보내지 못했어요: {describe_error(e.__cause__ or e)}")
            print("         발신번호를 솔라피에 등록했는지, 잔액이 있는지 확인하세요.")
            return False
    else:
        print(f"  {INFO} 실제로 한 통 받아 보려면:  python -m server.check --send 내휴대폰번호")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="건강한통 키 확인")
    ap.add_argument("--send", metavar="번호", help="이 번호로 시험 문자를 한 통 보낸다")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("건강한통 키 확인")
    env_file = SERVER_DIR / ".env"
    print(f"  설정 파일: {env_file} {'(있음)' if env_file.exists() else '(없음 - .env.example 을 복사해 만드세요)'}")
    try:
        s = Settings.load()
    except ConfigError as e:
        print(f"  {NO} 설정 오류: {e}")
        return 1
    print(f"  환경: {'개발용' if s.dev else '실제 서비스'}   사이트 주소: {s.public_url}")
    results = [check_kakao(s), check_sms(s, args.send)]
    print("\n" + ("모두 준비됐어요. 서버를 켜고 사이트에서 가입해 보세요." if all(results) else "위의 [확인 필요] 항목을 고친 뒤 다시 실행하세요."))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
