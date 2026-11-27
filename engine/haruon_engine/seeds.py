"""처음 시작할 때 넣는 기본 건강 정보 (콘텐츠 창고의 씨앗).

공공데이터가 쌓이기 전에도 매일 보낼 거리가 있도록 직접 쓴 정보들이다.
모두 'draft' 로 들어가며, 약사가 검토해서 승인해야 발송된다.
"""
from __future__ import annotations

import sqlite3

from .db import add_tip

SEED_TIPS = [
    # 약과 음식 궁합
    dict(key="grapefruit", category="medicine_food", tags=["혈압", "심장"],
         title="자몽은 일부 약과 함께 드시면 안 돼요",
         body="자몽이나 자몽주스는 일부 혈압약과 콜레스테롤약의 효과를 지나치게 세게 만들 수 있어요.",
         action="드시는 약이 있다면 자몽을 드셔도 되는지 약사에게 여쭤보기"),
    dict(key="warfarin-greens", category="medicine_food", tags=["심장"],
         title="피를 묽게 하는 약을 드시면 채소 양을 일정하게",
         body="시금치, 브로콜리, 청국장 같은 음식은 와파린의 효과에 영향을 줄 수 있어요. "
              "끊을 필요는 없고, 먹는 양을 갑자기 크게 바꾸지 않는 게 중요해요.",
         action="이 음식들은 평소 드시던 양만큼 꾸준히 드시기",
         caution="약은 의사와 상의 없이 조절하지 마세요."),
    dict(key="metformin-b12", category="medicine_food", tags=["당뇨"],
         title="당뇨약을 오래 드시면 비타민B12도 챙기세요",
         body="당뇨약 메트포르민을 오래 드시면 비타민B12가 부족해질 수 있어요. 손발 저림이 생기기도 해요.",
         action="다음 진료 때 비타민B12 검사가 필요한지 여쭤보기"),
    # 영양제 제대로 먹기
    dict(key="calcium-iron", category="supplement", tags=["뼈"],
         title="칼슘과 철분 영양제는 따로 드세요",
         body="두 영양제를 한꺼번에 드시면 서로 흡수를 방해해요.",
         action="한쪽은 아침, 한쪽은 저녁처럼 2시간 넘게 간격 두기"),
    dict(key="vitamin-d-meal", category="supplement", tags=["뼈"],
         title="비타민D는 식사 직후에 드세요",
         body="기름에 녹는 비타민이라, 빈속보다 식사와 함께 드실 때 흡수가 더 잘 돼요.",
         action="비타민D 드시는 시간을 아침 식사 직후로 바꾸기"),
    dict(key="thyroid-empty", category="supplement", tags=[],
         title="갑상선약은 빈속에, 영양제는 나중에",
         body="갑상선약은 아침 빈속에 드시는 게 좋아요. 칼슘이나 철분 영양제와 가까이 드시면 약 흡수가 줄 수 있어요.",
         action="칼슘·철분 영양제는 갑상선약보다 몇 시간 뒤에 드시기",
         caution="복용 시간은 처방한 의사나 약사 안내를 따르세요."),
    # 몸이 보내는 신호
    dict(key="protein-three-meals", category="body_signal", tags=["관절"],
         title="단백질은 세 끼에 나눠 드세요",
         body="나이가 들면 근육이 빨리 줄어요. 저녁에 고기를 몰아 드시는 것보다 세 끼에 나눠 드시는 게 근육을 지키는 데 더 좋아요.",
         action="내일 아침 식사에 달걀 하나 더하기",
         caution="콩팥 질환으로 단백질을 줄이라고 들으신 분은 의사 안내를 따르세요."),
    dict(key="morning-bp", category="body_signal", tags=["혈압"],
         title="집에서 혈압은 아침에 재세요",
         body="아침에 일어나 소변을 보고, 약을 드시기 전에 재는 게 가장 정확해요. 기록해 두면 진료 때 큰 도움이 돼요.",
         action="내일 아침 약 드시기 전에 혈압 재고 적어 두기"),
    # 생활 속 사고 예방
    dict(key="stand-up-3-steps", category="safety", tags=["혈압"],
         title="일어날 때는 3단계로 천천히",
         body="누워 있다 바로 일어나면 혈압이 갑자기 떨어져 어지러울 수 있어요. 낙상을 막는 가장 쉬운 방법이에요.",
         action="누워서, 앉아서 30초 쉬고, 천천히 일어서기"),
    dict(key="night-light", category="safety", tags=[],
         title="밤에 화장실 가는 길을 밝혀 두세요",
         body="어르신 낙상은 밤에 화장실에 가다가 많이 생겨요. 어두운 복도와 문턱이 위험해요.",
         action="침대에서 화장실까지 발밑 조명 하나 켜 두기"),
    # 나라에서 주는 혜택
    dict(key="pneumococcal-free", category="benefit", tags=["폐"],
         title="65세 이상은 폐렴구균 예방접종이 무료예요",
         body="가까운 보건소나 지정 의료기관에서 무료로 맞으실 수 있어요.",
         action="맞으셨는지 모르겠으면 보건소에 전화로 확인하기",
         source_name="질병관리청 예방접종도우미", source_url="https://nip.kdca.go.kr"),
    # 뇌와 감각 건강
    dict(key="hearing-tv", category="brain_sense", tags=["귀", "기억력"],
         title="TV 소리를 자꾸 키우신다면 청력 검사를",
         body="잘 안 들리면 대화가 줄고 뇌가 받는 자극도 줄어요. 여러 연구에서 난청을 치매 위험 요인 가운데 하나로 꼽아요.",
         action="가까운 이비인후과에서 청력 검사 받아 보기"),
    dict(key="wavy-lines", category="brain_sense", tags=["눈"],
         title="곧은 선이 휘어 보이면 안과에 가 보세요",
         body="문틀이나 바둑판 같은 곧은 선이 휘어 보이거나 가운데가 흐리게 보이면 눈 안쪽(망막)의 이상일 수 있어요.",
         action="한쪽 눈씩 가리고 문틀을 바라보며 확인해 보기",
         caution="갑자기 잘 안 보이면 바로 안과 진료를 받으세요."),
]


def load_seeds(conn: sqlite3.Connection) -> int:
    added = 0
    for s in SEED_TIPS:
        s = dict(s)
        key = s.pop("key")
        s.setdefault("caution", "")
        s.setdefault("source_name", "하루온 편집팀")
        if add_tip(conn, dedupe_key=f"seed:{key}", writer="seed", kind="evergreen",
                   status="draft", priority=50, **s) is not None:
            added += 1
    conn.commit()
    return added
