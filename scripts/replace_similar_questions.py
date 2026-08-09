from __future__ import annotations

import difflib
import itertools
import json
import os
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


# 파이프라인 작업 디렉터리. 기본값은 이 저장소의 루트이고, AIMONG_ROOT로 덮어쓴다.
ROOT = Path(os.environ.get("AIMONG_ROOT") or Path(__file__).resolve().parent.parent)
INPUT_JSON = ROOT / ".tmp" / "question-bank-1056-reviewed" / "question-bank-1056-starlevel-reviewed.json"
OUTPUT_DIR = ROOT / ".tmp" / "question-bank-1056-replaced"
OUTPUT_JSON = OUTPUT_DIR / "question-bank-1056-starlevel-replaced.json"
OUTPUT_REPORT = OUTPUT_DIR / "question-bank-1056-starlevel-replaced-report.md"
OUTPUT_BUNDLE = OUTPUT_DIR / "question-bank-1056-starlevel-replaced-bundle.zip"

TERM_DICTIONARY = [
    ("확증 편향", "이미 믿는 생각에 맞는 정보만 더 찾으려는 경향이에요."),
    ("비지도학습", "정답 이름표 없이 비슷한 것끼리 묶어 보며 배우는 방법이에요."),
    ("지도학습", "정답 이름표가 붙은 자료를 보고 배우는 방법이에요."),
    ("강화학습", "해 본 결과에 따라 보상이나 점수를 받으며 배우는 방법이에요."),
    ("딥러닝", "많은 자료를 보고 특징을 찾아 배우는 인공지능 학습 방법이에요."),
    ("생체정보", "얼굴, 목소리, 지문처럼 사람을 알아볼 수 있는 정보예요."),
    ("감정 인식", "표정이나 목소리 등을 보고 감정을 짐작하는 기술이에요."),
    ("이해관계자", "어떤 일의 결과로 이익이나 불편을 받는 사람이에요."),
    ("팩트체크", "말이나 정보가 사실인지 다시 확인하는 일이에요."),
    ("개인정보", "이름, 주소, 전화번호처럼 나를 알아볼 수 있게 하는 정보예요."),
    ("저작권", "만든 사람의 글, 그림, 음악 등을 보호하는 권리예요."),
    ("분류기", "비슷한 것끼리 종류를 나누는 도구예요."),
    ("알고리즘", "문제를 해결하기 위해 정해 둔 순서와 방법이에요."),
    ("딜레마", "어느 쪽도 쉽게 고르기 어려운 상황이에요."),
    ("다양성", "여러 종류가 고르게 섞여 있는 상태예요."),
    ("편향", "한쪽으로 치우쳐 생각하거나 판단하는 것이에요."),
    ("출처", "정보가 처음 나온 곳이에요."),
    ("근거", "어떤 생각이나 판단을 뒷받침하는 이유나 자료예요."),
    ("인식", "보고 듣고 알아차리는 것을 말해요."),
    ("자료", "컴퓨터가 배우거나 판단할 때 참고하는 글, 숫자, 그림 같은 정보예요."),
    ("SNS", "글이나 사진을 올리고 다른 사람과 소통하는 인터넷 서비스예요."),
    ("CCTV", "주변 모습을 영상으로 기록하는 감시 카메라예요."),
]


def multiple(question: str, options: list[str], answer: int, explanation: str) -> dict:
    return {
        "type": "MULTIPLE",
        "question": question,
        "options": options,
        "answer": answer,
        "explanation": explanation,
    }


def fill(question: str, options: list[str], answer: int, explanation: str) -> dict:
    return {
        "type": "FILL",
        "question": question,
        "options": options,
        "answer": [answer],
        "explanation": explanation,
    }


def ox(question: str, answer: bool, explanation: str) -> dict:
    return {
        "type": "OX",
        "question": question,
        "options": None,
        "answer": answer,
        "explanation": explanation,
    }


REPLACEMENTS = {
    "S0101": {
        "MULTIPLE": [
            multiple(
                "스팸 메일을 자동으로 걸러 주는 기능이 인공지능 사례에 가까운 까닭은 무엇일까요?",
                ["색이 화려해서예요.", "메일 내용을 보고 구별하기 때문이에요.", "전기를 쓰기 때문이에요.", "버튼이 많기 때문이에요."],
                1,
                "생활 속 인공지능은 겉모습보다 정보를 보고 판단하거나 구별하는 기능이 있는지가 중요해요.",
            ),
            multiple(
                "다음 중 사람의 말을 알아듣고 답을 도와주는 도구로 가장 알맞은 것은 무엇일까요?",
                ["스마트 스피커", "빈 공책", "종이 자", "줄자"],
                0,
                "사람의 말을 듣고 뜻을 파악해 반응하는 스마트 스피커는 생활 속 인공지능 사례예요.",
            ),
            multiple(
                "생활 속 도구가 인공지능인지 살필 때 가장 알맞은 기준은 무엇일까요?",
                ["얼마나 반짝이는지", "얼마나 무거운지", "어떤 정보를 보고 판단하는지", "버튼 색이 몇 개인지"],
                2,
                "생활 속 인공지능은 도구의 겉모양보다 정보를 바탕으로 어떤 판단을 하는지 살펴보면 좋아요.",
            ),
            multiple(
                "번역 앱이 인공지능 사례로 자주 소개되는 이유로 가장 알맞은 것은 무엇일까요?",
                ["문장을 다른 언어로 바꾸기 위해 뜻을 살피기 때문이에요.", "화면이 밝기 때문이에요.", "앱 이름이 짧기 때문이에요.", "휴대폰에 들어 있기 때문이에요."],
                0,
                "번역 앱은 문장의 뜻을 살펴 다른 언어로 바꾸므로 생활 속 인공지능 사례가 될 수 있어요.",
            ),
        ],
        "FILL": [
            fill(
                "번역 앱은 문장을 보고 알맞은 뜻을 ____해 다른 언어로 바꿔요.",
                ["판단", "포장", "무게", "색칠"],
                0,
                "인공지능은 입력된 정보를 보고 알맞은 판단을 내리는 데 쓰일 수 있어요.",
            ),
            fill(
                "카메라 앱이 꽃을 구별하려면 사진 속 특징을 먼저 ____해야 해요.",
                ["인식", "숨김", "복사", "삭제"],
                0,
                "사진 속 특징을 알아보는 일은 인공지능의 인식과 관련이 있어요.",
            ),
            fill(
                "스마트 스피커는 사람의 말을 듣고 알맞게 ____해요.",
                ["반응", "멈춤", "접기", "건너뛰기"],
                0,
                "생활 속 인공지능은 들은 말에 맞게 반응하는 기능을 도울 수 있어요.",
            ),
            fill(
                "스팸 메일을 걸러 주는 기능은 여러 메일을 보고 종류를 ____하는 일을 해요.",
                ["분류", "장식", "측정", "인쇄"],
                0,
                "메일을 종류별로 나누는 일은 생활 속 인공지능 활용 예가 될 수 있어요.",
            ),
            fill(
                "생활 속 인공지능을 찾을 때는 어떤 문제를 ____하는지 살펴보면 좋아요.",
                ["해결", "칠하기", "잠그기", "접기"],
                0,
                "도구가 어떤 문제를 해결하는지 살피면 인공지능의 쓰임을 더 잘 이해할 수 있어요.",
            ),
        ],
    },
    "S0102": {
        "MULTIPLE": [
            multiple(
                "계산기와 학습 기반 인공지능의 차이로 가장 알맞은 설명은 무엇일까요?",
                ["둘 다 항상 같은 예시를 외워요.", "계산기는 정해진 규칙을 따르고, 인공지능은 자료에서 패턴을 배울 수 있어요.", "계산기는 사진을 보고 배우고, 인공지능은 덧셈만 해요.", "둘 다 사람의 도움 없이 처음부터 모든 일을 알아요."],
                1,
                "규칙 기반 도구와 학습 기반 인공지능의 차이는 미리 정한 규칙을 따르는지, 자료에서 패턴을 배우는지에 있어요.",
            ),
            multiple(
                "사람이 모든 규칙을 하나씩 적기 어려워 학습 기반 인공지능이 특히 유리한 일은 무엇일까요?",
                ["여러 사진에서 강아지와 고양이를 구별하기", "2와 3을 더하기", "버튼을 누르면 불 켜기", "알람 시간을 정해 울리기"],
                0,
                "사진 분류처럼 경우가 매우 많은 일은 자료를 보고 배우는 학습 기반 방식이 잘 어울려요.",
            ),
            multiple(
                "다음 중 규칙 기반 방식에 가장 가까운 예는 무엇일까요?",
                ["'만약 비밀번호가 맞으면 문을 연다'는 규칙을 따르는 장치", "수많은 사진을 보고 새 동물을 구별하는 도구", "여러 음성을 듣고 말을 알아듣는 도구", "많은 글을 보고 문장을 추천하는 도구"],
                0,
                "사람이 미리 정한 조건을 그대로 따르는 방식은 규칙 기반 접근에 가까워요.",
            ),
        ],
    },
    "S0103": {
        "MULTIPLE": [
            multiple(
                "정답 이름표가 붙은 사진을 보고 배우는 방법은 무엇일까요?",
                ["지도학습", "비지도학습", "강화학습", "무작위학습"],
                0,
                "정답 이름표가 붙은 자료를 이용하는 학습 방법은 지도학습이에요.",
            ),
            multiple(
                "학습에 쓰지 않은 새 사진으로 다시 확인하는 이유로 가장 알맞은 것은 무엇일까요?",
                ["새 자료에서도 잘 맞히는지 보기 위해서예요.", "사진 수를 예쁘게 맞추기 위해서예요.", "정답을 숨기기 위해서예요.", "파일 이름을 바꾸기 위해서예요."],
                0,
                "새 자료로 확인해야 배운 내용을 처음 보는 상황에서도 잘 적용하는지 알 수 있어요.",
            ),
            multiple(
                "다음 중 강화학습의 예로 가장 알맞은 것은 무엇일까요?",
                ["게임 점수를 보며 더 좋은 움직임을 배우는 로봇", "이름표 없는 사진을 비슷한 것끼리 묶는 도구", "정답표가 붙은 꽃 사진을 보고 배우는 도구", "계산기를 눌러 답을 바로 구하는 도구"],
                0,
                "강화학습은 해 본 결과에 따라 보상이나 점수를 받으며 더 나은 행동을 배우는 방법이에요.",
            ),
            multiple(
                "정답 이름표 없이 비슷한 과일 사진끼리 모으는 활동은 어떤 학습과 가장 가까울까요?",
                ["비지도학습", "지도학습", "강화학습", "암기학습"],
                0,
                "정답 이름표 없이 비슷한 것끼리 묶는 활동은 비지도학습의 특징과 가까워요.",
            ),
            multiple(
                "지도학습에서 '사과', '레몬'처럼 붙여 주는 정보는 무엇일까요?",
                ["정답 이름표", "무게표", "가격표", "색연필"],
                0,
                "지도학습은 정답 이름표가 붙은 자료를 보고 배우는 방법이에요.",
            ),
        ],
    },
    "S0104": {
        "MULTIPLE": [
            multiple(
                "다음 중 딥러닝이 쓰이기 쉬운 장면으로 가장 알맞은 것은 무엇일까요?",
                ["사진 속 동물을 알아보는 기능", "종이 길이를 자로 재는 일", "연필 개수를 손으로 세는 일", "문을 손으로 여는 일"],
                0,
                "딥러닝은 사진처럼 복잡한 자료에서 특징을 찾아 인식하는 데 자주 쓰여요.",
            ),
            multiple(
                "딥러닝과 머신러닝의 관계를 가장 잘 설명한 것은 무엇일까요?",
                ["딥러닝은 머신러닝의 한 종류예요.", "머신러닝은 딥러닝보다 항상 더 작은 개념이에요.", "딥러닝은 계산기와 같은 뜻이에요.", "둘은 전혀 관계가 없어요."],
                0,
                "딥러닝은 머신러닝 안에 포함되는 한 방법이에요.",
            ),
            multiple(
                "인공 신경망을 이용한 학습이 특히 도움을 줄 수 있는 일은 무엇일까요?",
                ["음성에서 말을 알아듣기", "종이접기 순서만 그대로 보여 주기", "줄자 눈금을 읽기", "연필을 상자에 담기"],
                0,
                "음성 인식처럼 복잡한 패턴을 찾는 일은 딥러닝이 잘 활용되는 분야예요.",
            ),
        ],
    },
    "S0105": {
        "OX": [
            ox(
                "인공지능 답이 자신 있어 보여도 출처와 근거를 다시 확인하는 것이 좋아요.",
                True,
                "인공지능은 그럴듯하게 말해도 틀릴 수 있으므로 출처와 근거를 다시 확인해야 해요.",
            ),
            ox(
                "같은 질문을 해도 인공지능 답이 조금씩 달라질 수 있어요.",
                True,
                "인공지능 답은 상황이나 표현에 따라 달라질 수 있으므로 한 번 더 살피는 습관이 필요해요.",
            ),
            ox(
                "틀린 자료를 바탕으로 배우면 인공지능도 틀린 답을 낼 수 있어요.",
                True,
                "배운 자료가 부정확하면 결과도 부정확해질 수 있어요.",
            ),
            ox(
                "중요한 정보는 인공지능 답 하나만 보지 말고 다른 자료와 비교하는 것이 좋아요.",
                True,
                "여러 자료와 비교해야 틀린 정보를 더 잘 걸러 낼 수 있어요.",
            ),
            ox(
                "답이 길다고 해서 언제나 더 정확한 것은 아니에요.",
                True,
                "길이보다 사실과 근거가 더 중요해요.",
            ),
        ],
        "MULTIPLE": [
            multiple(
                "인공지능 답을 다시 확인해야 하는 이유로 가장 알맞은 것은 무엇일까요?",
                ["답에 틀린 내용이 섞일 수 있기 때문이에요.", "긴 답은 모두 맞기 때문이에요.", "어려운 단어가 많으면 늘 정확하기 때문이에요.", "한 번 나온 답은 바뀌지 않기 때문이에요."],
                0,
                "인공지능은 그럴듯한 말 속에 틀린 내용이 섞일 수 있어 다시 확인해야 해요.",
            ),
            multiple(
                "두 답이 서로 다를 때 가장 좋은 다음 행동은 무엇일까요?",
                ["근거와 출처를 비교해요.", "더 긴 답만 고릅니다.", "마음에 드는 답만 믿어요.", "둘 다 바로 사실이라고 정해요."],
                0,
                "답이 다르면 근거와 출처를 비교해 어느 쪽이 더 믿을 만한지 살펴봐야 해요.",
            ),
            multiple(
                "오래된 정보를 새 소식처럼 말한 답은 인공지능의 어떤 점을 보여 줄까요?",
                ["오래된 정보를 새 소식처럼 말하는 경우", "여러 자료를 비교해 다시 확인하는 경우", "정답표가 있는 사진을 배우는 경우", "문장을 짧게 요약하는 경우"],
                0,
                "인공지능은 최신 정보나 사실을 틀리게 말할 수 있어요.",
            ),
            multiple(
                "인공지능 답을 볼 때 가장 좋은 습관은 무엇일까요?",
                ["날짜와 출처를 함께 확인해요.", "어려운 말이 많으면 바로 믿어요.", "문장이 길면 더 정확하다고 정해요.", "한 번 읽고 바로 퍼뜨려요."],
                0,
                "날짜와 출처를 함께 확인하면 잘못된 정보를 줄일 수 있어요.",
            ),
        ],
    },
    "S0201": {
        "MULTIPLE": [
            multiple(
                "다음 중 하려는 일이 가장 분명하게 드러난 질문은 무엇일까요?",
                ["발표 시작 문장 2개를 만들어 줘.", "아무 말이나 해 줘.", "알아서 써 줘.", "길게 설명해 줘."],
                0,
                "무엇을 하려는지 드러나면 인공지능이 더 알맞은 답을 만들기 쉬워요.",
            ),
            multiple(
                "분류기 아이디어를 생각할 때 가장 먼저 정하면 좋은 것은 무엇일까요?",
                ["누구의 어떤 문제를 돕고 싶은지", "이름을 얼마나 멋지게 지을지", "배경색을 무엇으로 할지", "친구가 웃을지"],
                0,
                "좋은 아이디어는 먼저 누구를 돕고 어떤 문제를 해결할지부터 정하면 좋아요.",
            ),
            multiple(
                "다음 중 목적이 잘 드러난 질문으로 가장 알맞은 것은 무엇일까요?",
                ["환경 보호 포스터에 넣을 문구를 3개 만들어 줘.", "환경에 대해 말해 줘.", "아무거나 써 줘.", "길게 적어 줘."],
                0,
                "무엇에 쓸 답인지 드러나는 질문이 더 분명한 목적을 보여 줘요.",
            ),
            multiple(
                "질문의 목적이 분명하면 어떤 점이 좋아질까요?",
                ["필요한 답에 더 가까워져요.", "항상 더 길어지기만 해요.", "개인정보가 더 많이 들어가요.", "답의 뜻을 보지 않아도 돼요."],
                0,
                "목적이 분명하면 원하는 답과 더 잘 맞는 결과를 받을 수 있어요.",
            ),
            multiple(
                "다음 중 발표 준비라는 목적이 가장 잘 드러난 질문은 무엇일까요?",
                ["초등학생 발표용으로 인공지능을 3문장으로 설명해 줘.", "인공지능 알려 줘.", "아무 설명이나 써 줘.", "글을 길게 써 줘."],
                0,
                "발표용이라는 목적과 필요한 분량이 함께 보이면 더 알맞은 답을 받기 쉬워요.",
            ),
        ],
        "FILL": [
            fill(
                "좋은 질문은 내가 하려는 ____을 먼저 보여 줘요.",
                ["일", "색", "소리", "냄새"],
                0,
                "무엇을 하려는지 먼저 드러내면 질문의 목적이 더 분명해져요.",
            ),
        ],
    },
    "S0202": {
        "MULTIPLE": [
            multiple(
                "초등학생 발표용 답을 부탁할 때 가장 분명한 질문은 무엇일까요?",
                ["초등학생에게 설명할 수 있게, 예시 1개와 2문장으로 써 줘.", "쉽게 설명해 줘.", "짧게 써 줘.", "알아서 써 줘."],
                0,
                "대상, 길이, 형식을 함께 말하면 질문이 더 구체적이 돼요.",
            ),
            multiple(
                "답이 너무 길고 어렵게 나왔을 때 가장 좋은 행동은 무엇일까요?",
                ["초등학생 수준, 3문장, 쉬운 말처럼 조건을 더해 다시 물어요.", "화를 내고 끝내요.", "개인정보를 더 넣어요.", "그대로 복사해요."],
                0,
                "원하는 답을 받지 못했을 때는 조건을 더 분명하게 고쳐 물으면 좋아요.",
            ),
            multiple(
                "다음 중 질문에 넣어도 되는 안전한 조건은 무엇일까요?",
                ["표로 정리해 줘.", "우리 집 주소를 참고해 줘.", "친구 전화번호를 넣어 줘.", "반 친구 얼굴 사진을 기준으로 해 줘."],
                0,
                "형식 조건은 답을 다듬는 데 도움이 되지만 개인정보는 넣지 않아야 해요.",
            ),
            multiple(
                "같은 주제를 더 알맞게 묻는 질문으로 가장 좋은 것은 무엇일까요?",
                ["초등학생 발표용으로 4문장, 목록 형식으로 설명해 줘.", "그냥 설명해 줘.", "길게 알려 줘.", "대충 써 줘."],
                0,
                "대상과 길이, 형식이 함께 들어간 질문이 더 구체적이에요.",
            ),
        ],
        "FILL": [
            fill(
                "표, 목록, 문단처럼 답을 보여 줄 ____을 정하면 질문이 더 분명해져요.",
                ["형식", "무게", "온도", "냄새"],
                0,
                "답을 어떤 모습으로 받을지 정하면 인공지능이 더 알맞게 답하기 쉬워요.",
            ),
        ],
    },
    "S0203": {
        "MULTIPLE": [
            multiple(
                "다음 중 생체정보에 해당하는 것은 무엇일까요?",
                ["지문", "연필 색", "책 제목", "급식 메뉴"],
                0,
                "지문은 사람을 알아볼 수 있게 하는 생체정보예요.",
            ),
            multiple(
                "인공지능에게 글쓰기 도움을 받을 때 가장 안전한 행동은 무엇일까요?",
                ["실명 대신 가명을 써요.", "집 주소를 자세히 적어요.", "친구 전화번호를 넣어요.", "얼굴 사진을 함께 보내요."],
                0,
                "개인정보를 줄이고 가명이나 익명을 쓰는 편이 더 안전해요.",
            ),
            multiple(
                "얼굴 사진이나 목소리 정보를 조심해야 하는 이유로 가장 알맞은 것은 무엇일까요?",
                ["나를 알아볼 수 있게 하기 때문이에요.", "색이 예쁘기 때문이에요.", "파일이 작기 때문이에요.", "항상 재미있기 때문이에요."],
                0,
                "얼굴과 목소리는 사람을 식별하는 데 쓰일 수 있어 조심해야 해요.",
            ),
            multiple(
                "친구 사진을 인공지능 서비스에 올리기 전 가장 먼저 할 일은 무엇일까요?",
                ["친구의 허락을 받아요.", "바로 올려요.", "이름을 크게 적어요.", "사진을 여러 장 더 올려요."],
                0,
                "다른 사람의 사진을 쓸 때는 먼저 허락을 받아야 해요.",
            ),
            multiple(
                "다음 중 개인정보를 줄여 쓴 예로 가장 알맞은 것은 무엇일까요?",
                ["김민수 대신 '학생 A'라고 써요.", "집 주소를 모두 적어요.", "전화번호를 그대로 넣어요.", "지문 사진을 첨부해요."],
                0,
                "실명 대신 가명이나 익명 표현을 쓰면 개인정보 노출을 줄일 수 있어요.",
            ),
        ],
    },
    "S0204": {
        "MULTIPLE": [
            multiple(
                "음성 분류기를 만들 때 자료를 모으는 방법으로 가장 좋은 것은 무엇일까요?",
                ["여러 사람의 또렷한 목소리를 고르게 모아요.", "한 사람 목소리만 계속 모아요.", "잡음이 큰 녹음만 모아요.", "허락 없이 친구 목소리를 녹음해요."],
                0,
                "다양하고 또렷한 자료를 모아야 새로운 상황에서도 더 잘 작동할 수 있어요.",
            ),
            multiple(
                "테스트용 자료를 따로 두는 가장 큰 이유는 무엇일까요?",
                ["처음 보는 자료에서도 잘 되는지 확인하려고요.", "파일 개수를 맞추려고요.", "자료를 숨기려고요.", "정답을 없애려고요."],
                0,
                "학습에 쓰지 않은 자료로 확인해야 실제 상황에서의 성능을 더 잘 볼 수 있어요.",
            ),
            multiple(
                "다음 중 학습 자료로 쓰기 가장 어려운 사진은 무엇일까요?",
                ["심하게 흔들려 꽃 모양이 잘 보이지 않는 사진", "밝은 곳에서 찍은 꽃 사진", "옆에서 찍은 꽃 사진", "다른 배경의 꽃 사진"],
                0,
                "흐리거나 잘못된 자료는 학습 결과를 나쁘게 만들 수 있어요.",
            ),
            multiple(
                "인터넷 사진을 학습 자료로 쓰기 전에 먼저 확인할 것은 무엇일까요?",
                ["저작권과 사용 허락", "파일 이름 길이", "화면 밝기", "사진을 본 내 기분"],
                0,
                "다른 사람이 만든 자료를 쓸 때는 저작권과 사용 허락을 먼저 확인해야 해요.",
            ),
            multiple(
                "꽃 분류 자료를 고르게 모은 예로 가장 알맞은 것은 무엇일까요?",
                ["여러 각도와 여러 밝기의 꽃 사진을 함께 모아요.", "한 장면 사진만 수십 장 모아요.", "같은 꽃만 한 색으로만 찍어요.", "흐린 사진만 모아요."],
                0,
                "다양한 조건의 자료를 모아야 한쪽으로 치우친 학습을 줄일 수 있어요.",
            ),
            multiple(
                "학습 자료를 모을 때 출처를 적어 두면 좋은 이유는 무엇일까요?",
                ["나중에 어디서 가져왔는지 확인할 수 있어서예요.", "사진을 더 화려하게 만들 수 있어서예요.", "파일을 숨길 수 있어서예요.", "정답을 없앨 수 있어서예요."],
                0,
                "출처 기록은 자료를 바르게 사용했는지 확인하는 데 도움이 돼요.",
            ),
            multiple(
                "음성 자료를 모을 때 다양성을 높이는 방법으로 가장 알맞은 것은 무엇일까요?",
                ["여러 사람의 말소리를 고르게 모아요.", "한 사람 목소리만 반복해요.", "모든 소리를 아주 작게 녹음해요.", "배경 소음만 모아요."],
                0,
                "여러 사람의 목소리를 고르게 모아야 더 다양한 상황을 배울 수 있어요.",
            ),
            multiple(
                "반 친구 사진을 학습 자료로 쓰려면 가장 먼저 필요한 것은 무엇일까요?",
                ["친구와 보호자의 허락", "더 큰 파일 크기", "영어 파일 이름", "사진 수를 홀수로 맞추기"],
                0,
                "사람이 담긴 자료를 쓸 때는 허락과 개인정보 보호를 함께 생각해야 해요.",
            ),
            multiple(
                "밝은 곳과 어두운 곳의 사진을 함께 모으는 까닭은 무엇일까요?",
                ["여러 상황에서도 잘 구별하도록 돕기 위해서예요.", "사진 수를 줄이기 위해서예요.", "정답을 감추기 위해서예요.", "파일 이름을 맞추기 위해서예요."],
                0,
                "여러 조건의 자료가 있어야 실제 상황에서 더 잘 작동할 수 있어요.",
            ),
            multiple(
                "다음 중 자료를 바르게 모은 예로 가장 알맞은 것은 무엇일까요?",
                ["허락받은 사진을 출처와 함께 정리해요.", "인터넷 사진을 출처 없이 모두 저장해요.", "친구 목소리를 몰래 녹음해요.", "흐린 사진만 많이 모아요."],
                0,
                "허락과 출처를 함께 챙기는 것이 바른 자료 수집이에요.",
            ),
        ],
    },
    "S0205": {
        "MULTIPLE": [
            multiple(
                "강아지와 고양이 분류기가 자꾸 헷갈릴 때 가장 먼저 해 볼 일은 무엇일까요?",
                ["헷갈리는 예시를 더 모아 다시 학습해요.", "틀린 결과를 숨겨요.", "아무 것도 바꾸지 않아요.", "바로 포기해요."],
                0,
                "틀린 예시를 살펴 부족한 자료를 보완하면 더 나은 결과를 만들 수 있어요.",
            ),
            multiple(
                "공정한 실험 방법으로 가장 알맞은 것은 무엇일까요?",
                ["한 번에 한 조건만 바꾸고 결과를 비교해요.", "모든 조건을 한꺼번에 바꿔요.", "결과를 보지 않아요.", "느낌만 말해요."],
                0,
                "한 번에 하나씩 바꿔야 어떤 변화가 결과에 영향을 줬는지 알기 쉬워요.",
            ),
            multiple(
                "라벨을 고친 뒤 가장 알맞은 다음 행동은 무엇일까요?",
                ["새 자료로 다시 시험해요.", "바로 끝내요.", "틀린 결과를 지워요.", "기록을 없애요."],
                0,
                "고친 뒤에는 다시 시험해 변화가 실제로 도움이 되었는지 확인해야 해요.",
            ),
            multiple(
                "실험 중 바꾼 점을 기록해 두면 좋은 이유는 무엇일까요?",
                ["어떤 변화가 결과를 바꿨는지 알 수 있어서예요.", "점수를 숨길 수 있어서예요.", "시간을 더 오래 끌 수 있어서예요.", "정답을 줄일 수 있어서예요."],
                0,
                "기록이 있으면 어떤 수정이 효과가 있었는지 비교할 수 있어요.",
            ),
            multiple(
                "새 사진에서 오답이 많을 때 가장 도움이 되는 행동은 무엇일까요?",
                ["어떤 사진에서 자주 틀리는지 살펴봐요.", "오답을 모두 무시해요.", "버튼만 더 빨리 눌러요.", "점수만 크게 적어요."],
                0,
                "오답이 생긴 장면을 살펴보면 어떤 자료를 더 보완할지 알 수 있어요.",
            ),
        ],
    },
    "S0206": {
        "MULTIPLE": [
            multiple(
                "다음 중 내가 이해한 뒤 다시 쓴 답에 가장 가까운 것은 무엇일까요?",
                ["예시를 참고한 뒤 내가 이해한 말로 다시 써요.", "뜻도 모르고 그대로 붙여 넣어요.", "가장 긴 답만 고릅니다.", "친구 답과 똑같이 복사해요."],
                0,
                "인공지능은 생각을 돕는 도구로 쓰고, 마지막 표현은 내 말로 정리하는 것이 좋아요.",
            ),
            multiple(
                "인공지능이 초안을 만들어 준 뒤 가장 좋은 다음 행동은 무엇일까요?",
                ["내용을 이해하고 내 말로 고쳐요.", "바로 제출해요.", "뜻을 보지 않고 외워요.", "출처 없이 퍼뜨려요."],
                0,
                "초안은 참고 자료이고, 최종 답은 내가 이해한 말로 다듬어야 해요.",
            ),
            multiple(
                "친구의 피드백이 도움이 되는 까닭은 무엇일까요?",
                ["내 설명이 분명한지 다시 볼 수 있어서예요.", "글씨 크기만 바꿀 수 있어서예요.", "내용을 읽지 않아도 되어서예요.", "발표를 건너뛸 수 있어서예요."],
                0,
                "다른 사람의 반응을 들으면 내 답이 잘 전달되는지 확인할 수 있어요.",
            ),
            multiple(
                "다음 중 인공지능을 잘못 활용한 예는 무엇일까요?",
                ["어려운 단어 뜻을 모른 채 그대로 발표문에 넣어요.", "힌트를 받아 내 말로 고쳐요.", "예시를 보고 구조를 배워요.", "모르는 부분을 질문해요."],
                0,
                "뜻을 모른 채 그대로 쓰면 내 답이 아니고 이해도 부족할 수 있어요.",
            ),
            multiple(
                "인공지능 답에 낯선 단어가 나오면 가장 좋은 행동은 무엇일까요?",
                ["뜻을 확인하고 쉬운 말로 다시 써요.", "그대로 외워요.", "더 어려운 말로 바꿔요.", "친구에게도 그대로 복사해 줘요."],
                0,
                "내가 이해한 말로 바꾸려면 먼저 뜻을 확인해야 해요.",
            ),
            multiple(
                "예시 문장을 받은 뒤 가장 알맞은 활용 방법은 무엇일까요?",
                ["문장 구조를 참고해 내 생각을 새로 써요.", "문장을 그대로 여러 번 붙여요.", "누가 썼는지 보지 않아요.", "뜻을 지워 버려요."],
                0,
                "예시는 참고하되, 최종 문장은 내 생각을 담아 새로 써야 해요.",
            ),
            multiple(
                "최종 답이 '내 답'이라고 할 수 있는 가장 좋은 기준은 무엇일까요?",
                ["내가 뜻을 이해하고 직접 설명할 수 있어요.", "문장이 가장 길어요.", "어려운 단어가 많아요.", "그대로 복사했어요."],
                0,
                "내가 이해하고 설명할 수 있어야 내 답이라고 할 수 있어요.",
            ),
            multiple(
                "발표 전에 가장 도움이 되는 점검 방법은 무엇일까요?",
                ["내 말로 다시 설명해 봐요.", "더 어려운 단어를 넣어요.", "모르는 부분을 숨겨요.", "원문을 그대로 읽어요."],
                0,
                "내 말로 다시 설명해 보면 정말 이해했는지 확인할 수 있어요.",
            ),
        ],
    },
    "S0301": {
        "MULTIPLE": [
            multiple(
                "팩트체크를 시작할 때 가장 먼저 해야 할 일은 무엇일까요?",
                ["확인할 핵심 주장을 찾기", "문장 길이를 재기", "색을 예쁘게 칠하기", "친구가 좋아할지 묻기"],
                0,
                "사실 확인은 먼저 무엇을 확인할지, 핵심 주장을 찾는 데서 시작해요.",
            ),
            multiple(
                "어떤 말이 사실인지 확인할 때 먼저 던지면 좋은 질문은 무엇일까요?",
                ["이 말을 확인할 자료가 있을까?", "가장 멋져 보일까?", "글자가 많을까?", "친구가 놀랄까?"],
                0,
                "확인할 자료가 있는지 묻는 질문이 사실과 추측을 나누는 데 도움이 돼요.",
            ),
            multiple(
                "어떤 말이 사실인지 확인할 때 가장 도움이 되는 것은 무엇일까요?",
                ["관련 자료를 찾아 비교하기", "제목만 보기", "문장 길이만 보기", "가장 먼저 본 글만 믿기"],
                0,
                "여러 자료를 찾아 비교해야 사실 여부를 더 잘 확인할 수 있어요.",
            ),
            multiple(
                "한 자료만 보지 않고 여러 자료를 비교하는 까닭은 무엇일까요?",
                ["틀린 정보인지 더 잘 살피기 위해서예요.", "글을 더 길게 만들기 위해서예요.", "정답을 숨기기 위해서예요.", "색깔을 맞추기 위해서예요."],
                0,
                "여러 자료를 비교하면 한쪽 정보만 믿는 실수를 줄일 수 있어요.",
            ),
        ],
    },
    "S0302": {
        "MULTIPLE": [
            multiple(
                "다음 중 더 믿을 만한 자료에 가까운 것은 무엇일까요?",
                ["작성자와 날짜, 기관이 함께 적힌 자료", "작성자가 없는 짧은 글", "날짜가 없는 소문 글", "출처가 보이지 않는 이미지"],
                0,
                "누가 언제 어디에 썼는지 확인할 수 있는 자료가 더 믿을 만해요.",
            ),
            multiple(
                "출처를 살필 때 확인할 내용으로 가장 알맞은 것은 무엇일까요?",
                ["글쓴이와 날짜, 나온 곳", "글자 색", "문장 길이", "사진 개수"],
                0,
                "출처를 볼 때는 글쓴이, 날짜, 정보가 나온 곳을 함께 확인해야 해요.",
            ),
            multiple(
                "서로 다른 두 글을 함께 볼 때 가장 도움이 되는 행동은 무엇일까요?",
                ["같은 점과 다른 점을 나누어 적어요.", "긴 글만 믿어요.", "마음에 드는 글만 남겨요.", "그림 많은 글만 고릅니다."],
                0,
                "같은 점과 다른 점을 나누면 자료를 더 차분하게 비교할 수 있어요.",
            ),
            multiple(
                "두 자료의 날짜가 다를 때 먼저 생각할 점은 무엇일까요?",
                ["더 최근 자료인지 확인해요.", "글자 수가 많은지 봐요.", "색깔이 예쁜지 봐요.", "사진이 큰지 봐요."],
                0,
                "정보는 시기에 따라 달라질 수 있어 날짜를 함께 확인해야 해요.",
            ),
            multiple(
                "다음 중 근거가 더 분명한 문장은 무엇일까요?",
                ["조사 결과와 출처를 함께 제시한 문장", "그냥 그렇다고 말한 문장", "누가 썼는지 모르는 문장", "날짜가 없는 짧은 문장"],
                0,
                "근거와 출처가 함께 제시된 문장이 더 확인하기 쉬워요.",
            ),
            multiple(
                "자료를 소개할 때 함께 적으면 좋은 것은 무엇일까요?",
                ["정보가 나온 곳", "내 기분", "글씨 색", "문장 수"],
                0,
                "정보가 나온 곳을 적으면 다른 사람도 확인하기 쉬워요.",
            ),
        ],
    },
    "S0303": {
        "MULTIPLE": [
            multiple(
                "다음 중 자료가 한쪽으로 치우친 예로 가장 알맞은 것은 무엇일까요?",
                ["한 반 학생만 조사해 모든 어린이의 생각이라고 말해요.", "여러 지역 학생을 고르게 조사해요.", "다른 의견도 함께 모아요.", "자료 수집 방법을 적어 둬요."],
                0,
                "일부 집단만 조사하면 전체를 대표하지 못해 편향된 결과가 나올 수 있어요.",
            ),
        ],
        "FILL": [
            fill(
                "내 생각에 맞는 정보만 더 찾으려는 태도는 확증 ____이라고 해요.",
                ["편향", "기록", "검토", "출처"],
                0,
                "확증 편향은 이미 믿는 생각에 맞는 정보만 더 찾으려는 경향이에요.",
            ),
        ],
    },
    "S0304": {
        "MULTIPLE": [
            multiple(
                "같은 기술의 양면성을 살필 때 가장 좋은 태도는 무엇일까요?",
                ["도움이 되는 점과 걱정되는 점을 함께 봐요.", "좋은 점만 봐요.", "나쁜 점만 봐요.", "아무 영향도 없다고 정해요."],
                0,
                "같은 기술도 여러 영향을 줄 수 있으므로 좋은 점과 걱정되는 점을 함께 봐야 해요.",
            ),
            multiple(
                "다음 중 기술의 영향을 받는 사람을 넓게 살핀 예로 가장 알맞은 것은 무엇일까요?",
                ["학생, 교사, 보호자처럼 관련된 사람을 함께 생각해요.", "개발자 한 명만 봐요.", "컴퓨터 부품만 봐요.", "그림 파일만 봐요."],
                0,
                "기술은 여러 사람에게 영향을 줄 수 있어 관련된 사람을 함께 살펴야 해요.",
            ),
            multiple(
                "자동 번역 기술의 긍정적인 영향으로 가장 알맞은 것은 무엇일까요?",
                ["다른 언어 정보를 더 쉽게 이해할 수 있어요.", "사람을 몰래 감시할 수 있어요.", "개인정보를 더 많이 모을 수 있어요.", "의견을 한쪽으로만 보게 해요."],
                0,
                "자동 번역은 여러 언어의 정보를 더 쉽게 이해하도록 도울 수 있어요.",
            ),
            multiple(
                "추천 알고리즘을 쓸 때 함께 생각할 걱정거리로 알맞은 것은 무엇일까요?",
                ["비슷한 정보만 계속 보게 될 수 있어요.", "항상 모든 정보를 다 보게 돼요.", "개인정보와는 전혀 관계가 없어요.", "틀린 정보가 절대 나오지 않아요."],
                0,
                "추천 기능은 편리하지만 한쪽 정보만 보게 할 수도 있어요.",
            ),
            multiple(
                "새로운 인공지능 기술을 쓰기 전 물어보면 좋은 질문은 무엇일까요?",
                ["누구에게 도움이 되고 누구에게 불편할까?", "화면 색이 예쁠까?", "버튼이 몇 개일까?", "이름이 짧을까?"],
                0,
                "기술의 양면성을 보려면 영향을 받는 사람과 변화를 함께 생각해야 해요.",
            ),
            multiple(
                "다음 중 인공지능 기술의 부정적 영향에 가까운 것은 무엇일까요?",
                ["허락 없이 사람을 계속 감시해요.", "시각장애인을 위해 글을 읽어 줘요.", "다른 언어를 번역해 줘요.", "길 찾기를 도와줘요."],
                0,
                "도움이 되는 기술도 사생활 침해처럼 부정적 영향을 줄 수 있어요.",
            ),
            multiple(
                "배달 로봇이 도입될 때 함께 살펴볼 사람으로 가장 알맞은 것은 무엇일까요?",
                ["이용자, 보행자, 일하는 사람들", "로봇 색만 고르는 사람", "인터넷 그림 파일", "컴퓨터 부품만 만드는 사람"],
                0,
                "기술은 여러 이해관계자에게 영향을 줄 수 있으므로 넓게 살펴봐야 해요.",
            ),
            multiple(
                "기술의 좋은 점만 보고 바로 쓰면 놓치기 쉬운 것은 무엇일까요?",
                ["예상하지 못한 불편이나 피해", "버튼 개수", "글자 색", "파일 크기"],
                0,
                "기술의 양면성을 보려면 생길 수 있는 불편과 피해도 함께 생각해야 해요.",
            ),
            multiple(
                "같은 인공지능 기술을 사람마다 다르게 느낄 수 있는 이유는 무엇일까요?",
                ["받는 도움과 불편이 서로 다를 수 있어서예요.", "모든 사람이 같은 상황이라서예요.", "기술은 누구에게도 영향을 주지 않아서예요.", "항상 한 가지 결과만 있어서예요."],
                0,
                "사람마다 처한 상황이 달라 같은 기술의 영향도 다르게 느낄 수 있어요.",
            ),
            multiple(
                "기술을 평가할 때 가장 균형 잡힌 방법은 무엇일까요?",
                ["장점, 단점, 영향을 받는 사람을 함께 살펴요.", "장점만 적어요.", "단점만 적어요.", "제목만 보고 정해요."],
                0,
                "기술의 양면성을 이해하려면 여러 면을 함께 살펴야 해요.",
            ),
        ],
    },
    "S0305": {
        "MULTIPLE": [
            multiple(
                "다음 중 딜레마 상황에 가장 가까운 것은 무엇일까요?",
                ["자율주행차가 누구를 먼저 보호할지 정해야 하는 상황", "연필 색을 고르는 상황", "점심 메뉴를 고르는 상황", "창문을 몇 개 열지 정하는 상황"],
                0,
                "어느 선택도 쉽지 않고 사람에게 큰 영향을 줄 수 있는 상황이 딜레마에 가까워요.",
            ),
            multiple(
                "공정한 선택을 생각할 때 가장 먼저 할 일은 무엇일까요?",
                ["누가 영향을 받는지 찾기", "답이 긴 쪽 고르기", "가장 빠른 쪽 고르기", "친한 사람 편만 들기"],
                0,
                "공정한 선택을 고민하려면 먼저 영향을 받는 사람을 살펴야 해요.",
            ),
            multiple(
                "윤리적인 인공지능 설계에서 함께 생각할 기준으로 알맞은 것은 무엇일까요?",
                ["책임, 투명성, 사생활 보호", "화면 색, 글자 크기, 장식", "광고 수, 배경음, 글자 모양", "버튼 위치, 이름 길이, 그림 수"],
                0,
                "윤리적인 설계에서는 책임과 투명성, 사생활 보호 같은 기준을 함께 봐야 해요.",
            ),
            multiple(
                "딜레마 문제에 정답이 하나로 쉽지 않은 까닭은 무엇일까요?",
                ["서로 다른 사람에게 다른 영향이 생기기 때문이에요.", "항상 같은 답만 있기 때문이에요.", "색깔만 고르면 되기 때문이에요.", "누구도 영향을 받지 않기 때문이에요."],
                0,
                "여러 사람에게 미치는 영향이 달라 어떤 선택이 더 공정한지 고민이 필요해요.",
            ),
            multiple(
                "나라나 문화에 따라 딜레마 선택이 달라질 수 있음을 보여 주는 예로 알맞은 것은 무엇일까요?",
                ["보행자와 탑승자 중 누구를 더 우선할지 생각이 다를 수 있어요.", "모든 나라가 항상 같은 답만 골라요.", "딜레마는 문화와 전혀 관계없어요.", "사람들은 누구나 연필 색만 생각해요."],
                0,
                "교재의 Moral Machine 사례처럼 문화와 사회 규범에 따라 선택이 달라질 수 있어요.",
            ),
            multiple(
                "어려운 선택을 비교할 때 가장 도움이 되는 방법은 무엇일까요?",
                ["각 선택이 누구에게 어떤 영향을 주는지 적어 봐요.", "가장 짧은 답을 골라요.", "아무 이유 없이 빨리 정해요.", "한 사람 의견만 들어요."],
                0,
                "영향을 나누어 살피면 더 공정한 선택을 고민하기 쉬워요.",
            ),
            multiple(
                "다음 중 Moral Machine과 가장 가까운 질문은 무엇일까요?",
                ["자율주행차가 위험한 순간 누구를 보호해야 할까?", "연필을 어디에 둘까?", "컴퓨터 배경색을 무엇으로 할까?", "창문을 몇 개 열까?"],
                0,
                "Moral Machine은 자율주행차의 어려운 선택을 생각해 보는 사례예요.",
            ),
        ],
    },
}


def load_bank() -> dict:
    return json.loads(INPUT_JSON.read_text(encoding="utf-8"))


def similarity_targets(bank: dict) -> dict[str, dict[str, list[str]]]:
    by_mission = defaultdict(list)
    qmap = {question["externalId"]: question for question in bank["questions"]}
    for question in bank["questions"]:
        by_mission[question["missionCode"]].append(question)

    targets: dict[str, dict[str, list[str]]] = {}
    for mission_code, questions in by_mission.items():
        graph = defaultdict(set)
        for left, right in itertools.combinations(questions, 2):
            ratio = difflib.SequenceMatcher(None, left["question"], right["question"]).ratio()
            if ratio >= 0.9:
                graph[left["externalId"]].add(right["externalId"])
                graph[right["externalId"]].add(left["externalId"])

        seen = set()
        mission_targets = defaultdict(list)
        for node in sorted(graph):
            if node in seen:
                continue
            stack = [node]
            component = []
            seen.add(node)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in graph[current]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
            for external_id in sorted(component)[1:]:
                mission_targets[qmap[external_id]["type"]].append(external_id)
        if mission_targets:
            targets[mission_code] = dict(mission_targets)
    return targets


def update_term_hints(question: dict) -> None:
    search_text = " ".join([question.get("question") or "", " ".join(question.get("options") or [])])
    hints = []
    for term, description in TERM_DICTIONARY:
        if term in search_text and not any(existing["term"] == term for existing in hints):
            hints.append({"term": term, "description": description})
        if len(hints) == 3:
            break
    question["termHints"] = hints


def apply_replacements(bank: dict, targets: dict[str, dict[str, list[str]]]) -> list[dict]:
    qmap = {question["externalId"]: question for question in bank["questions"]}
    changes = []

    for mission_code, mission_targets in sorted(targets.items()):
        for question_type, external_ids in sorted(mission_targets.items()):
            candidates = REPLACEMENTS[mission_code][question_type]
            if len(candidates) != len(external_ids):
                raise ValueError(
                    f"replacement count mismatch for {mission_code}/{question_type}: "
                    f"need {len(external_ids)}, have {len(candidates)}"
                )
            for external_id, replacement in zip(external_ids, candidates, strict=True):
                question = qmap[external_id]
                before = {
                    "question": question["question"],
                    "options": question.get("options"),
                    "answer": question["answer"],
                    "explanation": question["explanation"],
                }
                question["question"] = replacement["question"]
                question["options"] = replacement["options"]
                question["answer"] = replacement["answer"]
                question["explanation"] = replacement["explanation"]
                update_term_hints(question)
                changes.append(
                    {
                        "externalId": external_id,
                        "missionCode": mission_code,
                        "type": question_type,
                        "before": before,
                        "after": {
                            "question": question["question"],
                            "options": question.get("options"),
                            "answer": question["answer"],
                            "explanation": question["explanation"],
                        },
                    }
                )
    return changes


def count_similar_pairs(bank: dict, threshold: float = 0.9) -> list[tuple[float, str, str, str]]:
    by_mission = defaultdict(list)
    for question in bank["questions"]:
        by_mission[question["missionCode"]].append(question)

    pairs = []
    for mission_code, questions in by_mission.items():
        for left, right in itertools.combinations(questions, 2):
            ratio = difflib.SequenceMatcher(None, left["question"], right["question"]).ratio()
            if ratio >= threshold:
                pairs.append((ratio, mission_code, left["externalId"], right["externalId"]))
    return sorted(pairs, reverse=True)


def validation_summary(bank: dict) -> dict:
    questions = bank["questions"]
    exact = defaultdict(list)
    answer_errors = []
    missing_required = []
    for question in questions:
        exact[question["question"]].append(question["externalId"])
        for field in ["externalId", "missionCode", "type", "question", "answer", "difficulty", "packNo"]:
            if field not in question:
                missing_required.append((question.get("externalId"), field))
        if question["type"] in {"MULTIPLE", "SITUATION"}:
            if not (
                isinstance(question.get("options"), list)
                and isinstance(question["answer"], int)
                and 0 <= question["answer"] < len(question["options"])
            ):
                answer_errors.append(question["externalId"])
        if question["type"] == "FILL":
            if not (
                isinstance(question.get("options"), list)
                and isinstance(question["answer"], list)
                and all(isinstance(index, int) and 0 <= index < len(question["options"]) for index in question["answer"])
            ):
                answer_errors.append(question["externalId"])

    term_counts = Counter()
    for question in questions:
        term_counts.update(hint["term"] for hint in question.get("termHints", []))

    return {
        "question_count": len(questions),
        "missing_required": len(missing_required),
        "answer_errors": len(answer_errors),
        "exact_duplicate_groups": sum(1 for ids in exact.values() if len(ids) > 1),
        "missing_term_hints": sum(1 for question in questions if "termHints" not in question),
        "questions_with_hints": sum(1 for question in questions if question.get("termHints")),
        "max_hints": max(len(question.get("termHints", [])) for question in questions),
        "term_counts": term_counts,
    }


def write_report(changes: list[dict], before_pairs: int, after_pairs: int, bank: dict) -> None:
    counts = Counter(change["missionCode"] for change in changes)
    validation = validation_summary(bank)
    lines = [
        "# 문제은행 유사 문항 교체 리포트",
        "",
        "## 요약",
        "",
        f"- 전체 문항 수: {validation['question_count']}개",
        f"- 교체 전 유사도 0.9 이상 쌍: {before_pairs}쌍",
        f"- 교체 후 유사도 0.9 이상 쌍: {after_pairs}쌍",
        f"- 실제 교체 문항 수: {len(changes)}개",
        f"- 어려운 용어 해설이 붙은 문항: {validation['questions_with_hints']}개",
        "",
        "## 참고 자료 반영 원칙",
        "",
        "- `KERIS 1` 교재의 생활 속 인공지능 사례, 학습 방법 구분, 딥러닝과 인식, 자료 수집, 양면성, 딜레마 내용을 기준으로 각 미션 범위를 벗어나지 않게 새 문항을 작성했습니다.",
        "- `S0201`, `S0202`, `S0206`은 기존 미션 설계와 프롬프트 학습 목표를 유지하면서, 같은 주제 안에서 질문의 목적·조건·자기 말로 정리하기를 다른 장면으로 물었습니다.",
        "- 문항 유형과 난이도 구조는 유지하고, 중복 체감을 줄이기 위해 질문 장면과 보기 구성을 함께 바꿨습니다.",
        "",
        "## 미션별 교체 수",
        "",
    ]
    for mission_code, count in sorted(counts.items()):
        lines.append(f"- `{mission_code}`: {count}개")

    lines.extend(["", "## 어려운 용어 해설 적용 현황", ""])
    for term, count in validation["term_counts"].most_common():
        lines.append(f"- `{term}`: {count}개 문항")

    lines.extend(
        [
            "",
            "## 최종 검증 결과",
            "",
            f"- 필수 필드 누락: {validation['missing_required']}건",
            f"- 정답 인덱스 오류: {validation['answer_errors']}건",
            f"- 완전 중복 문항 그룹: {validation['exact_duplicate_groups']}개",
            f"- 유사도 0.9 이상 문항 쌍: {after_pairs}쌍",
            f"- `termHints` 누락 문항: {validation['missing_term_hints']}개",
            f"- 문항당 최대 `termHints` 수: {validation['max_hints']}개",
        ]
    )

    lines.extend(["", "## 변경 예시", ""])
    for change in changes[:24]:
        lines.extend(
            [
                f"### {change['externalId']} ({change['missionCode']})",
                "",
                f"- 변경 전: {change['before']['question']}",
                f"- 변경 후: {change['after']['question']}",
                "",
            ]
        )

    lines.extend(
        [
            "## 산출물",
            "",
            f"- 교체본 JSON: `{OUTPUT_JSON.name}`",
            f"- 교체 리포트: `{OUTPUT_REPORT.name}`",
            f"- 묶음 파일: `{OUTPUT_BUNDLE.name}`",
            "",
        ]
    )
    OUTPUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(bank: dict, report_ready: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report_ready:
        with zipfile.ZipFile(OUTPUT_BUNDLE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(OUTPUT_JSON, OUTPUT_JSON.name)
            archive.write(OUTPUT_REPORT, OUTPUT_REPORT.name)


def main() -> None:
    bank = load_bank()
    targets = similarity_targets(bank)
    before_pairs = len(count_similar_pairs(bank))
    changes = apply_replacements(bank, targets)
    after_pairs = len(count_similar_pairs(bank))
    write_outputs(bank)
    write_report(changes, before_pairs, after_pairs, bank)
    write_outputs(bank, report_ready=True)
    print(f"changes={len(changes)}")
    print(f"before_pairs={before_pairs}")
    print(f"after_pairs={after_pairs}")
    print(f"output_json={OUTPUT_JSON}")
    print(f"output_report={OUTPUT_REPORT}")
    print(f"output_bundle={OUTPUT_BUNDLE}")


if __name__ == "__main__":
    main()
