# 건강한통 콘텐츠 엔진

공공데이터를 가져와 → AI가 어르신용 건강 정보 초안을 쓰고 → 약사가 검토·승인하면 →
받는 분마다 매일 **서로 다른 정보 여러 개**를 골라 아침에 보냅니다.

```
[매일 새벽] collect  공공데이터 5곳에서 새 자료 가져오기
            draft    새 자료를 AI가 3줄짜리 쉬운 글로 (초안)
[수시로]    review   약사가 검토 화면에서 고치고 승인 / 반려
[아침 7:30] plan     받는 분마다 오늘 보낼 정보 고르기
[아침 8:00] send     보내기 (지금은 파일로, 카카오톡은 연결 예정)
```

## 어떤 자료를 가져오나

| 자료원 | 공공데이터포털 이름 (번호) | 무엇에 쓰나 | 검토 |
|---|---|---|---|
| `weather` | 기상청_단기예보 조회서비스 (15084084) | 한파·폭염·일교차 큰 날 알림 | 문장 틀 자동 승인 |
| `air` | 한국환경공단_에어코리아_대기오염정보 (15073861) | 미세먼지 나쁜 날 알림 | 문장 틀 자동 승인 |
| `drug_easy` | 식품의약품안전처_의약품개요정보(e약은요) (15075057) | 약 먹을 때 피할 음식·술 | 약사 승인 필요 |
| `dur_elderly` | 식품의약품안전처_의약품안전사용서비스(DUR)품목정보 (15059486) | 어르신이 조심할 약 성분 | 약사 승인 필요 |
| `gov24` | 행정안전부_대한민국 공공서비스(혜택) 정보 (15113968) | 어르신 지원 제도 | 약사 승인 필요 |

- 날씨·미세먼지는 그날 그 지역 사람에게만 가고, 다른 정보보다 먼저 보내요.
- 약·혜택 자료는 한 번에 다 받지 않고 실행할 때마다 다음 페이지를 조금씩 읽어요. 같은 내용은 한 번만 저장돼요.
- 공공데이터가 쌓이기 전에도 보낼 수 있게 기본 정보 13개가 들어 있어요 (`haruon_engine/seeds.py`).

## 정보를 고르는 규칙 (planner)

1. 약사가 승인한 정보만 보내요.
2. 한 사람에게 같은 정보를 두 번 보내지 않아요.
3. 오늘 날씨·미세먼지 알림이 있으면 먼저 보내요.
4. 하루에 여러 개면 서로 다른 주제로 골라요 (약과 음식, 영양제, 몸의 신호, 사고 예방, 혜택, 뇌·감각).
5. 받는 분의 관심 건강(혈압, 당뇨 등)과 겹치는 정보, 요일 주제를 우선해요.
6. 최근 일주일에 많이 받은 주제는 뒤로 미뤄요.

하루 개수는 `.env`에서 정해요. 기본값은 무료 1개, 멤버십 3개예요.

## 처음 해 보기 (키 없이, 예시 자료로)

파이썬 3.10 이상이 필요해요. `engine` 폴더에서:

```powershell
python -m haruon_engine init
```
```powershell
python -m haruon_engine collect --sample
```
```powershell
python -m haruon_engine draft
```
```powershell
python -m haruon_engine review
```

마지막 명령을 실행하고 브라우저에서 http://127.0.0.1:8790 을 열면 검토 화면이 나와요. 승인한 다음:

```powershell
python -m haruon_engine plan --show
```
```powershell
python -m haruon_engine send
```

보낸 메시지는 `data/outbox/날짜/받는분.txt` 에 저장돼요. 예시 자료는 `samples/` 폴더에 있고, 실제 공공데이터가 아니에요.

## 실제 자료로 쓰기

1. **공공데이터포털 인증키**
   - [data.go.kr](https://www.data.go.kr) 에 가입한 뒤, 위 표의 5개 API를 각각 검색해서 **활용 신청**을 해요. 개발 계정은 대부분 바로 승인돼요.
   - 마이페이지의 **일반 인증키(Decoding)** 값을 복사해요. 발급 직후에는 1~2시간 뒤부터 동작할 수 있어요.
2. **Claude API 키** (AI 초안용, 선택)
   - [console.anthropic.com](https://console.anthropic.com) 에서 키를 만들어요. 키가 없으면 AI 없이 원문을 잘라 붙인 초안이 만들어지고, 약사가 직접 다듬어야 해요.
   - AI를 쓰려면 한 번만 설치하세요:
     ```powershell
     python -m pip install -r requirements.txt
     ```
3. `.env.example` 을 `.env` 로 복사하고 두 키를 넣어요. **키는 채팅이나 GitHub에 올리지 마세요.** `.env` 는 GitHub에 올라가지 않게 해 두었어요.
4. 받는 분 목록: `users.sample.json` 과 같은 형식으로 파일을 만들어 넣어요.
   ```powershell
   python -m haruon_engine init --users 내_회원목록.json
   ```

## 매일 자동으로 돌리기

윈도우 **작업 스케줄러**에 아래 세 가지를 등록하면 돼요 (리눅스 서버라면 cron).

| 시각 | 명령 | 하는 일 |
|---|---|---|
| 05:30 | `python -m haruon_engine collect` 후 `python -m haruon_engine draft` | 새 자료와 초안 |
| 07:30 | `python -m haruon_engine plan` | 오늘 보낼 정보 고르기 |
| 08:00 | `python -m haruon_engine send` | 보내기 |

새벽에 만든 초안은 약사가 승인한 뒤 **다음 날부터** 보내져요. 그날 아침에 보내는 건 미리 승인해 둔 정보와 날씨·미세먼지 알림이에요. 그래서 약사는 하루 한 번, 편한 시간에 검토하면 돼요.

## 명령어

| 명령 | 하는 일 |
|---|---|
| `init [--users 파일]` | 데이터베이스 만들기, 기본 정보·받는 분 넣기 |
| `collect [--sample] [--only 자료원] [--date 날짜]` | 공공데이터 가져오기 |
| `draft [--limit N]` | 초안 만들기 |
| `review [--port 8790]` | 약사 검토 화면 |
| `plan [--date 날짜] [--show] [--dry-run]` | 보낼 정보 고르기 |
| `send [--date 날짜]` | 보내기 |
| `daily [--sample]` | collect + draft + plan 한 번에 |
| `status` | 쌓인 양 보기 |
| `list [--status draft]`, `approve 번호…`, `reject 번호 --note 이유` | 명령어로 검토 |

`approve --all-drafts` 는 검토 없이 전부 승인하는 **테스트용** 명령이에요. 실제 운영에서는 쓰지 마세요.

## 파일 구조

| 파일 | 내용 |
|---|---|
| `haruon_engine/config.py` | API 주소, 지역(날씨 격자), 주제, 설정 값 |
| `haruon_engine/sources/` | 자료원 5곳 (weather, air, drug_easy, dur, gov24) |
| `haruon_engine/templates.py` | 날씨·미세먼지 알림 문장 틀 |
| `haruon_engine/writer.py` | AI 초안 작성과 금지 표현 검사 |
| `haruon_engine/seeds.py` | 처음 넣는 기본 정보 13개 |
| `haruon_engine/planner.py` | 받는 분마다 정보 고르기 |
| `haruon_engine/messages.py` | 카카오톡 메시지 글 모양 |
| `haruon_engine/senders.py` | 보내기 (파일 / 카카오톡 자리) |
| `haruon_engine/review_server.py` | 약사 검토 화면 |
| `samples/` | 키 없이 시험할 때 쓰는 예시 응답 |

## 실제 키로 처음 돌릴 때 확인할 것

포털 설명 페이지에 경로나 응답 필드가 다 나오지 않은 곳이 있어서, 처음 실제로 돌릴 때 한 번 확인해 주세요.

- **DUR 노인주의**: 경로 `getOdsnAtentInfoList03` 과 응답 필드(`INGR_KOR_NAME`, `PROHBT_CONTENT` 등)를 포털의 미리보기로 확인. 틀리면 `.env` 에 `ENDPOINT_DUR_ELDERLY=` 로 고치고, 필드는 `sources/dur.py` 에서 고쳐요.
- **에어코리아**: 경로 `getCtprvnRltmMesureDnsty` 확인.
- **정부24 혜택**: 주소 `api.odcloud.kr/api/gov24/v3/serviceList` 와 응답의 `data` 목록 확인.
- **날씨 격자**: `config.py` 의 `REGIONS` 값을 기상청 API 활용가이드의 격자 엑셀로 확인.
- 실패하면 `collect` 가 이유를 쉬운 말로 알려 주고, 다른 자료원은 계속 진행해요.

## 비용

- 공공데이터 API는 무료예요. 개발 계정은 API마다 하루 호출 수 제한이 있어서 `PAGES_PER_RUN` 으로 조절해요.
- AI 초안은 하루 10건 기준으로 한 달 몇만 원 안쪽이 예상돼요. 실제 사용량으로 확인하세요. `MAX_DRAFTS_PER_RUN` 으로 하루 최대 건수를 정할 수 있어요.

## 아직 할 일

- [ ] 카카오톡 발송 연결 (`senders.py` 의 `KakaoSender`)
- [ ] 회원 정보를 사이트 가입·결제와 연결
- [ ] 날씨·미세먼지 문장 틀과 기본 정보 13개 약사 검토
- [ ] 건강기능식품 정보 자료원 추가 (영양제 주제)
