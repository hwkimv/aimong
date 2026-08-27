"""Convert validated question-bank JSON into the backend payload shape.

Two conversions matter here:

1. Answer indexes are stored 0-based in the dataset and 1-based in
   private.question_answer_keys, so every index is shifted on the way out.
2. Each question is bound to the mission set it belongs to. The backend serves
   a fixed set through question_bank.set_id, so a question exported without a
   set_id is invisible to set-based serving.
"""

from __future__ import annotations

import hashlib
from typing import Any

ADAPTER_VERSION = "v2.0"


def java_name_uuid(seed: str) -> str:
    """Match java.util.UUID.nameUUIDFromBytes so ids stay stable across reseeds."""
    data = bytearray(hashlib.md5(seed.encode("utf-8")).digest())
    data[6] = (data[6] & 0x0F) | 0x30
    data[8] = (data[8] & 0x3F) | 0x80
    hexed = data.hex()
    return f"{hexed[:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:]}"


def question_id(external_id: str) -> str:
    return java_name_uuid(f"question:{external_id}")


def mission_id(mission_code: str) -> str:
    return java_name_uuid(f"mission:{mission_code}")


def set_id(mission_code: str, pack_no: int) -> str:
    """mission_sets.set_id for a pack, e.g. S0101 pack 3 -> 'S0101-L3'."""
    return f"{mission_code}-L{pack_no}"


def star_level(pack_no: int) -> int:
    return ((pack_no - 1) // 2) + 1


def variant_no(pack_no: int) -> int:
    return 1 if pack_no % 2 == 1 else 2


def answer_payload(question: dict[str, Any]) -> Any:
    """Dataset indexes are 0-based; the backend answer key is 1-based."""
    question_type = question["type"]
    answer = question["answer"]
    if question_type in {"MULTIPLE", "SITUATION"}:
        return int(answer) + 1
    if question_type == "FILL":
        return [int(item) + 1 for item in answer]
    return answer


def mission_sort_key(mission: dict[str, Any]) -> tuple[int, int, str]:
    code = str(mission.get("missionCode", ""))
    try:
        stage = int(mission.get("stage", code[1:3]))
    except (TypeError, ValueError):
        stage = 0
    try:
        number = int(code[3:5])
    except ValueError:
        number = 0
    return stage, number, code


def normalize_question(question: dict[str, Any], mission: dict[str, Any]) -> dict[str, Any]:
    pack_no = question["packNo"]
    mission_code = question["missionCode"]
    return {
        "externalId": question["externalId"],
        "id": question_id(question["externalId"]),
        "missionCode": mission_code,
        "missionId": mission_id(mission_code),
        "setId": set_id(mission_code, pack_no),
        "stage": question.get("stage", mission.get("stage")),
        "missionTitle": question.get("missionTitle", mission.get("missionTitle")),
        "packNo": pack_no,
        "type": question["type"],
        "difficulty": question["difficulty"],
        "question": question["question"],
        "options": None if question["type"] == "OX" else question.get("options"),
        "answer": question["answer"],
        "answerPayload": answer_payload(question),
        "explanation": question["explanation"],
        "contentTags": question.get("contentTags", []),
        "curriculumRef": question.get("curriculumRef"),
        "sourceType": question["sourceType"],
        "generationPhase": question["generationPhase"],
        "sourceReference": question.get("sourceReference"),
    }


def build_mission_sets(missions: list[dict[str, Any]], contract: dict[str, Any]) -> list[dict[str, Any]]:
    """One mission_sets row per pack.

    question_count is the number of questions *served* per attempt, which the
    schema pins to 10. Pack 6 holds 16 candidates and the backend selects 10 of
    them, so the pool size and the served size are intentionally different.
    """
    served_per_set = 10
    rows: list[dict[str, Any]] = []
    for mission in sorted(missions, key=mission_sort_key):
        code = mission["missionCode"]
        stage = int(mission.get("stage") or code[1:3])
        number = int(code[3:5])
        for pack_no in range(1, contract["structure"]["packsPerMission"] + 1):
            rows.append(
                {
                    "setId": set_id(code, pack_no),
                    "missionId": mission_id(code),
                    "missionCode": code,
                    "starLevel": star_level(pack_no),
                    "variantNo": variant_no(pack_no),
                    "stage": stage,
                    "title": mission.get("missionTitle"),
                    "description": mission.get("missionSummary") or "",
                    "questionCount": served_per_set,
                    "displayOrder": stage * 1000 + number * 10 + pack_no,
                }
            )
    return rows


def build_payload(bank: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Assemble the backend payload. Callers must validate the contract first."""
    mission_map = {m["missionCode"]: m for m in bank["missions"]}
    questions = [normalize_question(q, mission_map.get(q["missionCode"], {})) for q in bank["questions"]]
    questions.sort(key=lambda item: item["externalId"])

    missions = [
        {
            "missionCode": mission["missionCode"],
            "missionId": mission_id(mission["missionCode"]),
            "stage": mission.get("stage"),
            "missionTitle": mission.get("missionTitle"),
            "missionSummary": mission.get("missionSummary"),
        }
        for mission in sorted(bank["missions"], key=mission_sort_key)
    ]

    return {
        "adapterVersion": ADAPTER_VERSION,
        "contractVersion": contract["contractVersion"],
        "generationVersion": bank.get("generationVersion"),
        "sourceTitle": bank.get("sourceTitle"),
        "questionCount": len(questions),
        "missions": missions,
        "missionSets": build_mission_sets(bank["missions"], contract),
        "questions": questions,
    }
