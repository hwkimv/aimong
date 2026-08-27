from __future__ import annotations

import difflib
import json
import os
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


# 파이프라인 작업 디렉터리. 기본값은 이 저장소의 루트이고, AIMONG_ROOT로 덮어쓴다.
ROOT = Path(os.environ.get("AIMONG_ROOT") or Path(__file__).resolve().parent.parent)
SOURCE_DIR = ROOT / ".tmp" / "question-bank-1056"
OUTPUT_DIR = ROOT / ".tmp" / "question-bank-1056-reviewed"

SOURCE_JSON = SOURCE_DIR / "question-bank-1056-starlevel-edits.json"
SOURCE_SQL = SOURCE_DIR / "question-bank-1056-starlevel-edits-seed.sql"
REVIEWED_JSON = OUTPUT_DIR / "question-bank-1056-starlevel-reviewed.json"
REVIEWED_REPORT = OUTPUT_DIR / "question-bank-1056-starlevel-reviewed-report.md"
REVIEWED_SQL = OUTPUT_DIR / "question-bank-1056-starlevel-edits-seed.sql"
REVIEWED_BUNDLE = OUTPUT_DIR / "question-bank-1056-starlevel-reviewed-bundle.zip"


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


def load_bank() -> dict:
    return json.loads(SOURCE_JSON.read_text(encoding="utf-8"))


def add_term_hints(bank: dict) -> Counter:
    term_counter: Counter[str] = Counter()
    questions_with_hints = 0

    for question in bank["questions"]:
        search_text = " ".join(
            [
                question.get("question") or "",
                " ".join(question.get("options") or []),
            ]
        )
        hints = []
        for term, description in TERM_DICTIONARY:
            if term in search_text and not any(existing["term"] == term for existing in hints):
                hints.append({"term": term, "description": description})
            if len(hints) == 3:
                break

        question["termHints"] = hints
        if hints:
            questions_with_hints += 1
            term_counter.update(hint["term"] for hint in hints)

    term_counter["__questions_with_hints__"] = questions_with_hints
    return term_counter


def duplicate_audit(bank: dict) -> dict:
    exact_global = defaultdict(list)
    exact_mission = defaultdict(list)
    same_options_mission = defaultdict(list)
    by_mission = defaultdict(list)

    for question in bank["questions"]:
        exact_global[question["question"]].append(question["externalId"])
        exact_mission[(question["missionCode"], question["question"])].append(question["externalId"])
        by_mission[question["missionCode"]].append(question)
        if question.get("options"):
            same_options_mission[(question["missionCode"], tuple(question["options"]))].append(question["externalId"])

    similar_pairs = []
    for mission_questions in by_mission.values():
        for index, left in enumerate(mission_questions):
            for right in mission_questions[index + 1 :]:
                ratio = difflib.SequenceMatcher(None, left["question"], right["question"]).ratio()
                if ratio >= 0.94:
                    similar_pairs.append(
                        {
                            "ratio": ratio,
                            "missionCode": left["missionCode"],
                            "leftId": left["externalId"],
                            "rightId": right["externalId"],
                            "leftQuestion": left["question"],
                            "rightQuestion": right["question"],
                        }
                    )

    similar_pairs.sort(key=lambda item: item["ratio"], reverse=True)

    return {
        "exact_global_groups": [ids for ids in exact_global.values() if len(ids) > 1],
        "exact_mission_groups": [ids for ids in exact_mission.values() if len(ids) > 1],
        "same_options_mission_groups": [ids for ids in same_options_mission.values() if len(ids) > 1],
        "similar_pairs": similar_pairs,
    }


def write_report(bank: dict, term_counter: Counter, audit: dict) -> None:
    total_questions = len(bank["questions"])
    questions_with_hints = term_counter.pop("__questions_with_hints__")
    lines = [
        "# 문제은행 1056문항 검토 리포트",
        "",
        "## 요약",
        "",
        f"- 전체 문항 수: {total_questions}개",
        f"- 같은 문장 완전 중복 그룹(전체): {len(audit['exact_global_groups'])}개",
        f"- 같은 미션 안 완전 중복 그룹: {len(audit['exact_mission_groups'])}개",
        f"- 같은 미션 안 동일 보기 세트 반복 그룹: {len(audit['same_options_mission_groups'])}개",
        f"- 문장 유사도 0.94 이상 후보 쌍: {len(audit['similar_pairs'])}쌍",
        f"- `termHints`가 추가된 문항: {questions_with_hints}개",
        "",
        "## 판단",
        "",
        "- 완전히 같은 문제 문장은 현재 검토본에서 발견되지 않았습니다.",
        "- 유사도 후보는 남아 있지만, 말끝만 바뀐 문항과 긍정/부정 대조 문항이 함께 잡혀 자동 교체 대상으로 바로 보기는 어렵습니다.",
        "- 그래서 이번 검토본에서는 원본 문항을 보존하고, 어려운 용어 설명을 `termHints` 형식으로 추가했습니다.",
        "- 참고 자료를 바탕으로 새 문항을 만드는 단계는 완전 중복을 해결하지 못했을 때의 후속 작업으로 남겨 두었습니다.",
        "",
        "## 어려운 용어 보강설명 형식",
        "",
        "```json",
        "{",
        '  "termHints": [',
        "    {",
        '      "term": "비지도학습",',
        '      "description": "정답 이름표 없이 비슷한 것끼리 묶어 보며 배우는 방법이에요."',
        "    }",
        "  ]",
        "}",
        "```",
        "",
        "## termHints 적용 결과",
        "",
    ]

    for term, count in term_counter.most_common():
        lines.append(f"- `{term}`: {count}개 문항")

    lines.extend(
        [
            "",
            "## 유사 문항 후보 예시",
            "",
        ]
    )

    for item in audit["similar_pairs"][:12]:
        lines.extend(
            [
                f"### {item['missionCode']} / 유사도 {item['ratio']:.3f}",
                "",
                f"- `{item['leftId']}`: {item['leftQuestion']}",
                f"- `{item['rightId']}`: {item['rightQuestion']}",
                "",
            ]
        )

    lines.extend(
        [
            "## 산출물",
            "",
            f"- 검토본 JSON: `{REVIEWED_JSON.name}`",
            f"- 기존 seed SQL 사본: `{REVIEWED_SQL.name}`",
            f"- 검토 리포트: `{REVIEWED_REPORT.name}`",
            f"- 묶음 파일: `{REVIEWED_BUNDLE.name}`",
            "",
            "## 메모",
            "",
            "- 이번 산출물은 원본 JSON/SQL을 덮어쓰지 않는 별도 검토본입니다.",
            "- `termHints`는 문제/보기에서 감지된 용어만 최대 3개까지 붙입니다.",
            "- 새 문제 생성이 필요해지면 참고 PDF와 각 미션 주제를 기준으로 별도 교체본을 만들면 됩니다.",
            "",
        ]
    )

    REVIEWED_REPORT.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(bank: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REVIEWED_JSON.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(SOURCE_SQL, REVIEWED_SQL)


def main() -> None:
    bank = load_bank()
    term_counter = add_term_hints(bank)
    audit = duplicate_audit(bank)
    write_outputs(bank)
    write_report(bank, term_counter, audit)
    with zipfile.ZipFile(REVIEWED_BUNDLE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(REVIEWED_JSON, REVIEWED_JSON.name)
        archive.write(REVIEWED_SQL, REVIEWED_SQL.name)
        archive.write(REVIEWED_REPORT, REVIEWED_REPORT.name)

    print(f"reviewed_json={REVIEWED_JSON}")
    print(f"reviewed_report={REVIEWED_REPORT}")
    print(f"reviewed_bundle={REVIEWED_BUNDLE}")
    print(f"exact_global_groups={len(audit['exact_global_groups'])}")
    print(f"exact_mission_groups={len(audit['exact_mission_groups'])}")
    print(f"same_options_mission_groups={len(audit['same_options_mission_groups'])}")
    print(f"similar_pairs_ge_094={len(audit['similar_pairs'])}")


if __name__ == "__main__":
    main()
