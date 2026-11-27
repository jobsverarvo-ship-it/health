"""공공데이터 API 호출과 응답 정리.

data.go.kr API는 응답 모양이 조금씩 달라서(body.items 가 목록이거나,
items.item 이거나, [{item: {...}}] 이거나) 한 곳에서 정리한다.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "haruon-engine/0.1"

# data.go.kr 에서 자주 나오는 오류를 쉬운 말로
KNOWN_ERRORS = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "인증키가 등록되지 않았어요. 발급 직후라면 1~2시간 뒤에 다시 해 보세요. "
                                           "포털의 '일반 인증키(Decoding)' 값을 넣었는지도 확인하세요.",
    "SERVICE_ACCESS_DENIED_ERROR": "이 API에 활용 신청이 안 되어 있어요. 포털에서 활용 신청을 해 주세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "오늘 호출 한도를 넘었어요. 내일 다시 하거나 PAGES_PER_RUN 을 줄이세요.",
    "NO_OPENAPI_SERVICE_ERROR": "API 주소가 맞지 않아요. config.py 또는 .env 의 ENDPOINT_ 값을 확인하세요.",
}


class ApiError(Exception):
    pass


def get_json(url: str, params: dict, *, timeout: float = 20, retries: int = 2) -> dict | list:
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}"
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            return _parse(text)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            if e.code in (401, 403):
                raise ApiError(f"인증 실패 (HTTP {e.code}). 인증키와 활용 신청을 확인하세요. {_short(body)}") from e
            if e.code < 500:
                raise ApiError(f"요청 오류 (HTTP {e.code}): {_short(body)}") from e
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise ApiError(f"API에 연결하지 못했어요: {last}")


def _parse(text: str) -> dict | list:
    stripped = text.lstrip()
    if stripped.startswith("<"):
        # 오류는 JSON을 요청해도 XML로 오는 경우가 많다
        code = _xml_value(stripped, "returnAuthMsg") or _xml_value(stripped, "resultMsg") or _xml_value(stripped, "errMsg")
        for key, msg in KNOWN_ERRORS.items():
            if key in stripped:
                raise ApiError(msg)
        raise ApiError(f"JSON 대신 XML 응답이 왔어요: {code or _short(stripped)}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ApiError(f"응답을 읽지 못했어요: {_short(text)}") from e
    _check_header(data)
    return data


def _check_header(data) -> None:
    if not isinstance(data, dict):
        return
    node = data.get("response", data)
    header = node.get("header") if isinstance(node, dict) else None
    if isinstance(header, dict):
        code = str(header.get("resultCode", "00"))
        if code not in ("00", "0", "INFO-000", "INFO-0"):
            msg = header.get("resultMsg", "")
            if code == "03" or "NODATA" in str(msg).upper():
                return  # 데이터 없음은 오류가 아님
            raise ApiError(f"API 오류 {code}: {msg}")


def extract_items(data) -> list[dict]:
    """data.go.kr 응답에서 항목 목록만 꺼낸다."""
    if isinstance(data, list):
        return data
    node = data.get("response", data)
    body = node.get("body", node)
    items = body.get("items", [])
    if not items:
        return []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    out = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("item"), dict):
            out.append(it["item"])
        elif isinstance(it, dict):
            out.append(it)
    return out


def pick(d: dict, *keys: str, default: str = "") -> str:
    """키 이름의 대소문자가 달라도 값을 꺼낸다."""
    lowered = {k.lower(): v for k, v in d.items()}
    for key in keys:
        v = lowered.get(key.lower())
        if v not in (None, ""):
            return str(v)
    return default


_TAG_RE = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    """원문에 섞인 HTML 태그와 줄바꿈을 정리한다."""
    text = _TAG_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _xml_value(xml: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.S)
    return m.group(1).strip() if m else None


def _short(text: str, n: int = 200) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:n] + ("…" if len(text) > n else "")
