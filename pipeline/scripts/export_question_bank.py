#!/usr/bin/env python3
# SUPERSEDED. Kept as the reference for the failure this pipeline was rebuilt to fix.
#
# Running this against data/question-bank-1056.json with config/mission-config.json
# reports verdict=FAIL with 99 issues: the config still describes the earlier
# 960-question plan, its allowedContentTags list is missing six tags the data uses,
# the pack expectation double-prefixes "P" so it compares PP1..PP6 against P1..P6,
# and the total-count check silently never runs because it reads globalPlan
# ["totalQuestions"] while the config key is "totalQuestionCount".
#
# The maintained implementation is pipeline/src/aimong_qbank; run `make verify`.
"""Export AImong rich question-bank JSON to backend-compatible artifacts.

Inputs:
  - rich JSON: final-question-bank.rich.json style output from the generation pipeline
  - mission-config.json: mission/topic/distribution contract

Outputs:
  - backend-compatible-question-bank.json
  - question-bank-seed.sql
  - adapter-smoke-report.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ADAPTER_VERSION = "v1.0"
QUESTION_TYPES = {"OX", "MULTIPLE", "FILL", "SITUATION"}
DIFFICULTIES = {"LOW", "MEDIUM", "HIGH"}
SOURCE_TYPES = {"STATIC", "GPT"}
GENERATION_PHASES = {"PREGENERATED", "RUNTIME"}
EXTERNAL_ID_RE = re.compile(r"^S\d{4}-P([1-6])-\d{2}$")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def java_name_uuid(seed: str) -> str:
    """Match Java UUID.nameUUIDFromBytes for deterministic seed IDs."""
    data = bytearray(hashlib.md5(seed.encode("utf-8")).digest())
    data[6] = (data[6] & 0x0F) | 0x30
    data[8] = (data[8] & 0x3F) | 0x80
    hexed = data.hex()
    return f"{hexed[:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:]}"


def sql_string(value: Any) -> str:
    if value is None:
        return "NULL"
    text = str(value)
    tag = "$aimong$"
    if tag in text:
        tag = "$aimong_sql$"
    return f"{tag}{text}{tag}"


def sql_json(value: Any) -> str:
    return sql_string(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def sql_jsonb(value: Any) -> str:
    return f"{sql_json(value)}::jsonb"


def answer_payload(question: dict[str, Any]) -> Any:
    question_type = question["type"]
    answer = question["answer"]
    if question_type in {"MULTIPLE", "SITUATION"}:
        return int(answer) + 1
    if question_type == "FILL":
        return [int(item) + 1 for item in answer]
    return answer


def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: collections.Counter[str] = collections.Counter()
    for item in items:
        value = item.get(key)
        if isinstance(value, list):
            counter.update(str(part) for part in value)
        elif value is not None:
            counter[str(value)] += 1
    return dict(sorted(counter.items()))


def mission_sort_key(mission: dict[str, Any]) -> tuple[int, int, str]:
    code = str(mission.get("missionCode", ""))
    try:
        stage = int(mission.get("stage", code[1:3]))
    except (TypeError, ValueError):
        stage = 0
    try:
        mission_no = int(code[3:5])
    except ValueError:
        mission_no = 0
    return stage, mission_no, code


def expected_totals_from_config(config: dict[str, Any]) -> dict[str, Any]:
    global_plan = config.get("globalPlan", {})
    missions = config.get("missions", [])
    expected = {
        "questionCount": global_plan.get("totalQuestions"),
        "missionCount": global_plan.get("missions"),
        "questionsPerMission": global_plan.get("questionsPerMission"),
        "typeCounts": global_plan.get("typeDistribution", {}),
        "difficultyCounts": global_plan.get("difficultyDistribution", {}),
        "packCounts": global_plan.get("packDistribution", {}),
    }
    if not expected["typeCounts"]:
        type_counts: collections.Counter[str] = collections.Counter()
        for mission in missions:
            type_counts.update(mission.get("typePlan", {}))
        expected["typeCounts"] = dict(sorted(type_counts.items()))
    if not expected["difficultyCounts"]:
        difficulty_counts: collections.Counter[str] = collections.Counter()
        for mission in missions:
            difficulty_counts.update(mission.get("difficultyPlan", {}))
        expected["difficultyCounts"] = dict(sorted(difficulty_counts.items()))
    if not expected["packCounts"]:
        pack_counts: collections.Counter[str] = collections.Counter()
        for mission in missions:
            pack_counts.update({f"P{k}": v for k, v in mission.get("packPlan", {}).items()})
        expected["packCounts"] = dict(sorted(pack_counts.items()))
    return expected


def mission_lookup(config: dict[str, Any], rich_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for mission in config.get("missions", []):
        code = mission.get("missionCode")
        if code:
            lookup[code] = dict(mission)
    for mission in rich_data.get("missions", []):
        code = mission.get("missionCode")
        if code:
            merged = dict(lookup.get(code, {}))
            merged.update(mission)
            lookup[code] = merged
    return lookup


def normalize_missions(config: dict[str, Any], rich_data: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = mission_lookup(config, rich_data)
    missions: list[dict[str, Any]] = []
    for code, mission in sorted(lookup.items(), key=lambda item: mission_sort_key(item[1])):
        missions.append(
            {
                "missionCode": code,
                "stage": mission.get("stage"),
                "chapterTitle": mission.get("chapterTitle"),
                "missionTitle": mission.get("missionTitle"),
                "missionSummary": mission.get("missionSummary"),
                "targetSkills": mission.get("targetSkills", []),
                "contentTags": mission.get("contentTags", []),
            }
        )
    return missions


def as_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_question_shape(
    question: dict[str, Any],
    mission_map: dict[str, dict[str, Any]],
    allowed_tags: set[str],
    issues: list[str],
    warnings: list[str],
) -> None:
    external_id = question.get("externalId")
    prefix = external_id or "<missing externalId>"
    required_string_fields = ["externalId", "missionCode", "type", "difficulty", "question", "explanation", "curriculumRef"]
    for field in required_string_fields:
        if not as_nonempty_string(question.get(field)):
            issues.append(f"{prefix}: missing or empty {field}")

    if as_nonempty_string(external_id):
        match = EXTERNAL_ID_RE.match(external_id)
        if not match:
            issues.append(f"{prefix}: externalId must look like S0101-P1-01")
        elif int(match.group(1)) != int(question.get("packNo", -1)):
            issues.append(f"{prefix}: externalId pack and packNo do not match")

    mission_code = question.get("missionCode")
    if mission_code not in mission_map:
        issues.append(f"{prefix}: unknown missionCode {mission_code}")

    question_type = question.get("type")
    if question_type not in QUESTION_TYPES:
        issues.append(f"{prefix}: unsupported type {question_type}")

    if question.get("difficulty") not in DIFFICULTIES:
        issues.append(f"{prefix}: unsupported difficulty {question.get('difficulty')}")

    source_type = question.get("sourceType")
    if source_type not in SOURCE_TYPES:
        issues.append(f"{prefix}: sourceType must be one of {sorted(SOURCE_TYPES)}")

    generation_phase = question.get("generationPhase")
    if generation_phase not in GENERATION_PHASES:
        issues.append(f"{prefix}: generationPhase must be one of {sorted(GENERATION_PHASES)}")

    pack_no = question.get("packNo")
    if not isinstance(pack_no, int) or not 1 <= pack_no <= 6:
        issues.append(f"{prefix}: packNo must be an integer from 1 to 6")

    tags = question.get("contentTags")
    if not isinstance(tags, list) or not tags:
        issues.append(f"{prefix}: contentTags must be a non-empty list")
    else:
        if len(tags) > 3:
            warnings.append(f"{prefix}: contentTags has more than 3 values")
        for tag in tags:
            if tag not in allowed_tags:
                issues.append(f"{prefix}: unsupported contentTag {tag}")

    options = question.get("options")
    answer = question.get("answer")
    if question_type == "OX":
        if options not in (None, []):
            issues.append(f"{prefix}: OX options must be null or empty")
        if not isinstance(answer, bool):
            issues.append(f"{prefix}: OX answer must be boolean")
    elif question_type in {"MULTIPLE", "SITUATION"}:
        if not isinstance(options, list) or len(options) != 4:
            issues.append(f"{prefix}: {question_type} options must have exactly 4 choices")
        if not isinstance(answer, int) or not 0 <= answer <= 3:
            issues.append(f"{prefix}: {question_type} answer must be 0-base integer 0..3")
    elif question_type == "FILL":
        if not isinstance(options, list) or len(options) not in {4, 5}:
            issues.append(f"{prefix}: FILL options must have 4 or 5 choices")
        if not isinstance(answer, list) or not answer:
            issues.append(f"{prefix}: FILL answer must be a non-empty 0-base integer list")
        elif isinstance(options, list):
            for item in answer:
                if not isinstance(item, int) or not 0 <= item < len(options):
                    issues.append(f"{prefix}: FILL answer index {item} is outside options")


def normalize_question(
    question: dict[str, Any],
    mission_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mission = mission_map.get(question.get("missionCode"), {})
    normalized = {
        "externalId": question.get("externalId"),
        "missionCode": question.get("missionCode"),
        "stage": question.get("stage", mission.get("stage")),
        "chapterTitle": question.get("chapterTitle", mission.get("chapterTitle")),
        "missionTitle": question.get("missionTitle", mission.get("missionTitle")),
        "packNo": question.get("packNo"),
        "type": question.get("type"),
        "difficulty": question.get("difficulty"),
        "question": question.get("question"),
        "options": question.get("options"),
        "answer": question.get("answer"),
        "answerPayload": None,
        "explanation": question.get("explanation"),
        "contentTags": question.get("contentTags", []),
        "curriculumRef": question.get("curriculumRef"),
        "sourceType": question.get("sourceType", "GPT"),
        "generationPhase": question.get("generationPhase", "PREGENERATED"),
        "sourceReference": question.get("sourceReference"),
        "targetSkill": question.get("targetSkill"),
        "contextCategory": question.get("contextCategory"),
        "termHints": question.get("termHints", []),
    }
    if normalized["options"] == [] and normalized["type"] == "OX":
        normalized["options"] = None
    if normalized["type"] in QUESTION_TYPES:
        try:
            normalized["answerPayload"] = answer_payload(normalized)
        except (TypeError, ValueError):
            normalized["answerPayload"] = None
    return normalized


def compare_count(
    label: str,
    actual: Any,
    expected: Any,
    issues: list[str],
    warnings: list[str],
    allow_sample: bool,
) -> None:
    if expected in (None, {}, []):
        return
    if actual != expected:
        message = f"{label}: expected {expected}, got {actual}"
        if allow_sample:
            warnings.append(message)
        else:
            issues.append(message)


def convert(
    rich_data: dict[str, Any],
    config: dict[str, Any],
    allow_sample: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    issues: list[str] = []
    warnings: list[str] = []
    raw_questions = rich_data.get("questions")
    if not isinstance(raw_questions, list):
        issues.append("root.questions must be a list")
        raw_questions = []

    allowed_tags = set(config.get("allowedContentTags") or config.get("globalPlan", {}).get("allowedContentTags", []))
    mission_map = mission_lookup(config, rich_data)
    normalized_questions = [normalize_question(item, mission_map) for item in raw_questions]

    for question in normalized_questions:
        validate_question_shape(question, mission_map, allowed_tags, issues, warnings)
        if question.get("answerPayload") is None:
            issues.append(f"{question.get('externalId', '<missing externalId>')}: answerPayload conversion failed")

    missions = normalize_missions(config, rich_data)
    mission_counts = count_by(normalized_questions, "missionCode")
    type_counts = count_by(normalized_questions, "type")
    difficulty_counts = count_by(normalized_questions, "difficulty")
    pack_counts = count_by(
        [{"pack": f"P{item.get('packNo')}"} for item in normalized_questions if item.get("packNo") is not None],
        "pack",
    )
    expected = expected_totals_from_config(config)

    compare_count("questionCount", len(normalized_questions), expected.get("questionCount"), issues, warnings, allow_sample)
    compare_count("missionCount", len(missions), expected.get("missionCount"), issues, warnings, allow_sample)
    compare_count("typeCounts", type_counts, expected.get("typeCounts"), issues, warnings, allow_sample)
    compare_count("difficultyCounts", difficulty_counts, expected.get("difficultyCounts"), issues, warnings, allow_sample)
    compare_count("packCounts", pack_counts, expected.get("packCounts"), issues, warnings, allow_sample)

    expected_per_mission = expected.get("questionsPerMission")
    if expected_per_mission:
        expected_mission_codes = {mission["missionCode"] for mission in missions if mission.get("missionCode")}
        short_or_long = {
            code: count
            for code, count in sorted(mission_counts.items())
            if count != expected_per_mission
        }
        missing_missions = {
            code: 0
            for code in sorted(expected_mission_codes - set(mission_counts))
        }
        per_mission_mismatch = {**missing_missions, **short_or_long}
        if per_mission_mismatch:
            message = f"questionsPerMission: expected {expected_per_mission} each, got {per_mission_mismatch}"
            if allow_sample:
                warnings.append(message)
            else:
                issues.append(message)

    backend_data = {
        "adapterVersion": ADAPTER_VERSION,
        "generationVersion": rich_data.get("generationVersion") or config.get("guideVersion"),
        "sourceTitle": rich_data.get("sourceTitle") or "AImong AI literacy question bank",
        "questionCount": len(normalized_questions),
        "missions": missions,
        "questions": sorted(normalized_questions, key=lambda item: str(item.get("externalId", ""))),
    }
    report = {
        "verdict": "FAIL" if issues else "PASS",
        "adapterVersion": ADAPTER_VERSION,
        "questionCount": len(normalized_questions),
        "missionCount": len(missions),
        "typeCounts": type_counts,
        "difficultyCounts": difficulty_counts,
        "packCounts": pack_counts,
        "missionCounts": dict(sorted(mission_counts.items())),
        "questionBankRows": len(normalized_questions),
        "answerKeyRows": len(normalized_questions),
        "answerConversionSample": [
            {
                "externalId": item.get("externalId"),
                "type": item.get("type"),
                "answer": item.get("answer"),
                "answerPayload": item.get("answerPayload"),
            }
            for item in backend_data["questions"][:8]
        ],
        "warnings": warnings,
        "issues": issues,
    }
    return backend_data, report


def export_seed(data: dict[str, Any], source_name: str = "backend-compatible-question-bank.json") -> str:
    missions = data["missions"]
    questions = data["questions"]
    mission_rows: list[str] = []
    set_rows: list[str] = []
    question_rows: list[str] = []
    answer_rows: list[str] = []
    mission_ids: dict[str, str] = {}

    for mission in sorted(missions, key=mission_sort_key):
        code = mission["missionCode"]
        mission_id = java_name_uuid(f"mission:{code}")
        mission_ids[code] = mission_id
        stage = int(mission.get("stage") or code[1:3])
        mission_no = int(code[3:5])
        mission_rows.append(
            "("
            f"'{mission_id}',"
            f"{stage},"
            f"{sql_string(mission.get('missionTitle'))},"
            f"{sql_string(code)},"
            f"{sql_string(mission.get('missionSummary'))},"
            "NULL,"
            "TRUE"
            ")"
        )
        for pack_no in range(1, 7):
            set_id = f"{code}-L{pack_no}"
            star_level = ((pack_no - 1) // 2) + 1
            variant_no = 1 if pack_no % 2 == 1 else 2
            display_order = stage * 1000 + mission_no * 10 + pack_no
            set_rows.append(
                "("
                f"{sql_string(set_id)},"
                f"'{mission_id}',"
                f"{sql_string(code)},"
                f"{star_level},"
                f"{variant_no},"
                f"{stage},"
                f"{sql_string(mission.get('missionTitle'))},"
                f"{sql_string(mission.get('missionSummary'))},"
                "10,"
                f"{display_order},"
                "TRUE"
                ")"
            )

    for question in questions:
        qid = java_name_uuid(f"question:{question['externalId']}")
        mission_id = mission_ids[question["missionCode"]]
        question_rows.append(
            "("
            f"'{qid}',"
            f"'{mission_id}',"
            "NULL,"
            f"{sql_string(question['type'])}::question_type_enum,"
            f"{sql_string(question['difficulty'])}::question_difficulty_enum,"
            f"{sql_string(question['question'])},"
            f"{sql_jsonb(question.get('options'))},"
            f"{sql_jsonb(question.get('contentTags', []))},"
            f"{sql_string(question.get('curriculumRef'))},"
            f"{sql_string(question.get('sourceType', 'GPT'))}::question_source_enum,"
            f"{sql_string(question.get('generationPhase', 'PREGENERATED'))}::question_generation_phase_enum,"
            f"{int(question.get('packNo'))},"
            f"{sql_string('ACTIVE')}::question_pool_status_enum,"
            "NOW(),"
            "TRUE"
            ")"
        )
        answer_rows.append(
            "("
            f"'{qid}',"
            f"{sql_jsonb(question['answerPayload'])},"
            f"{sql_string(question.get('explanation'))},"
            "NOW()"
            ")"
        )

    mission_codes = [mission["missionCode"] for mission in missions]
    sql: list[str] = [
        "-- AImong question-bank seed SQL",
        f"-- Generated by export_question_bank.py {ADAPTER_VERSION}",
        f"-- Source: {source_name}",
        f"-- question_bank rows: {len(question_rows)}",
        f"-- question_answer_keys rows: {len(answer_rows)}",
        "",
        "BEGIN;",
        "",
        "INSERT INTO public.missions (id, stage, title, mission_code, description, unlock_condition, is_active)",
        "VALUES",
        ",\n".join(mission_rows),
        "ON CONFLICT (mission_code) DO UPDATE SET",
        "  stage = EXCLUDED.stage,",
        "  title = EXCLUDED.title,",
        "  description = EXCLUDED.description,",
        "  unlock_condition = EXCLUDED.unlock_condition,",
        "  is_active = TRUE;",
        "",
        "UPDATE public.missions",
        "SET is_active = FALSE",
        "WHERE mission_code NOT IN (",
        "  " + ", ".join(sql_string(code) for code in mission_codes),
        ");",
        "",
        "INSERT INTO public.mission_sets (",
        "  set_id, mission_id, mission_code, star_level, variant_no, stage, title, description, question_count, display_order, is_active",
        ")",
        "VALUES",
        ",\n".join(set_rows),
        "ON CONFLICT (set_id) DO UPDATE SET",
        "  mission_id = EXCLUDED.mission_id,",
        "  mission_code = EXCLUDED.mission_code,",
        "  star_level = EXCLUDED.star_level,",
        "  variant_no = EXCLUDED.variant_no,",
        "  stage = EXCLUDED.stage,",
        "  title = EXCLUDED.title,",
        "  description = EXCLUDED.description,",
        "  question_count = EXCLUDED.question_count,",
        "  display_order = EXCLUDED.display_order,",
        "  is_active = TRUE;",
        "",
        "INSERT INTO public.question_bank (",
        "  id, mission_id, set_id, question_type, difficulty, prompt, options, content_tags,",
        "  curriculum_ref, source_type, generation_phase, pack_no, question_pool_status, created_at, is_active",
        ")",
        "VALUES",
        ",\n".join(question_rows),
        "ON CONFLICT (id) DO UPDATE SET",
        "  set_id = EXCLUDED.set_id,",
        "  mission_id = EXCLUDED.mission_id,",
        "  question_type = EXCLUDED.question_type,",
        "  difficulty = EXCLUDED.difficulty,",
        "  prompt = EXCLUDED.prompt,",
        "  options = EXCLUDED.options,",
        "  content_tags = EXCLUDED.content_tags,",
        "  curriculum_ref = EXCLUDED.curriculum_ref,",
        "  source_type = EXCLUDED.source_type,",
        "  generation_phase = EXCLUDED.generation_phase,",
        "  pack_no = EXCLUDED.pack_no,",
        "  question_pool_status = EXCLUDED.question_pool_status,",
        "  is_active = TRUE;",
        "",
        "INSERT INTO private.question_answer_keys (question_id, answer_payload, explanation, created_at)",
        "VALUES",
        ",\n".join(answer_rows),
        "ON CONFLICT (question_id) DO UPDATE SET",
        "  answer_payload = EXCLUDED.answer_payload,",
        "  explanation = EXCLUDED.explanation;",
        "",
        "COMMIT;",
        "",
    ]
    return "\n".join(sql)


def build_self_test_data(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "generationVersion": "self-test",
        "sourceTitle": "adapter self-test",
        "missions": config.get("missions", [])[:3],
        "questions": [
            {
                "externalId": "S0101-P1-01",
                "missionCode": "S0101",
                "packNo": 1,
                "type": "OX",
                "difficulty": "LOW",
                "question": "AI는 사람이 정한 목표에 맞게 데이터를 활용해 결과를 만들 수 있다.",
                "options": None,
                "answer": True,
                "explanation": "AI는 학습한 데이터와 규칙을 바탕으로 결과를 만든다.",
                "contentTags": ["FACT"],
                "curriculumRef": "adapter self-test",
                "sourceType": "GPT",
                "generationPhase": "PREGENERATED",
            },
            {
                "externalId": "S0101-P1-02",
                "missionCode": "S0101",
                "packNo": 1,
                "type": "MULTIPLE",
                "difficulty": "LOW",
                "question": "다음 중 AI가 할 수 있는 일로 가장 알맞은 것은?",
                "options": ["무작위로만 답하기", "데이터에서 규칙 찾기", "전기를 만들기", "책장을 넘기기"],
                "answer": 1,
                "explanation": "AI는 데이터에서 규칙이나 특징을 찾아 활용한다.",
                "contentTags": ["FACT"],
                "curriculumRef": "adapter self-test",
                "sourceType": "GPT",
                "generationPhase": "PREGENERATED",
            },
            {
                "externalId": "S0201-P2-01",
                "missionCode": "S0201",
                "packNo": 2,
                "type": "FILL",
                "difficulty": "MEDIUM",
                "question": "개인정보를 안전하게 다루려면 ( ) 정보는 함부로 입력하지 않는다.",
                "options": ["이름", "비밀", "날씨", "색깔"],
                "answer": [0, 1],
                "explanation": "이름이나 비밀번호처럼 나를 알아볼 수 있거나 보호해야 하는 정보는 조심해야 한다.",
                "contentTags": ["PRIVACY"],
                "curriculumRef": "adapter self-test",
                "sourceType": "GPT",
                "generationPhase": "PREGENERATED",
            },
            {
                "externalId": "S0303-P3-01",
                "missionCode": "S0303",
                "packNo": 3,
                "type": "SITUATION",
                "difficulty": "HIGH",
                "question": "친구가 AI에게 '숙제 알려줘'라고만 물었다. 더 좋은 질문으로 알맞은 것은?",
                "options": [
                    "숙제를 대신 해줘",
                    "초등학생이 이해할 수 있게 풀이 순서를 설명해줘",
                    "아무 답이나 해줘",
                    "질문하지 않는다",
                ],
                "answer": 1,
                "explanation": "대상과 원하는 결과를 구체적으로 말하면 AI 답변이 더 좋아진다.",
                "contentTags": ["PROMPT"],
                "curriculumRef": "adapter self-test",
                "sourceType": "GPT",
                "generationPhase": "PREGENERATED",
            },
        ],
    }


def run_self_test(config_path: Path) -> int:
    config = read_json(config_path)
    backend_data, report = convert(build_self_test_data(config), config, allow_sample=True)
    sql = export_seed(backend_data, "self-test")
    expected_payloads = {
        "S0101-P1-01": True,
        "S0101-P1-02": 2,
        "S0201-P2-01": [1, 2],
        "S0303-P3-01": 2,
    }
    actual_payloads = {item["externalId"]: item["answerPayload"] for item in backend_data["questions"]}
    if report["issues"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if actual_payloads != expected_payloads:
        print(f"SELF_TEST FAIL: answer payload mismatch {actual_payloads}", file=sys.stderr)
        return 1
    required_sql_tokens = [
        "public.question_bank",
        "private.question_answer_keys",
        java_name_uuid("question:S0101-P1-01"),
    ]
    missing_tokens = [token for token in required_sql_tokens if token not in sql]
    if missing_tokens:
        print(f"SELF_TEST FAIL: SQL missing {missing_tokens}", file=sys.stderr)
        return 1
    print("SELF_TEST PASS")
    print(f"sampleQuestions={report['questionCount']}")
    print(f"answerPayloads={json.dumps(actual_payloads, ensure_ascii=False, sort_keys=True)}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export rich AImong question-bank JSON to backend-compatible JSON and SQL.")
    parser.add_argument("--input", type=Path, help="Path to final-question-bank.rich.json")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("mission-config.json"))
    parser.add_argument("--out-dir", type=Path, default=Path.cwd())
    parser.add_argument("--backend-json", default="backend-compatible-question-bank.json")
    parser.add_argument("--seed-sql", default="question-bank-seed.sql")
    parser.add_argument("--report", default="adapter-smoke-report.json")
    parser.add_argument("--allow-sample", action="store_true", help="Allow partial/sample inputs while keeping field validation strict.")
    parser.add_argument("--self-test", action="store_true", help="Run an in-memory adapter smoke test.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        return run_self_test(args.config)
    if not args.input:
        print("--input is required unless --self-test is used", file=sys.stderr)
        return 2

    config = read_json(args.config)
    rich_data = read_json(args.input)
    backend_data, report = convert(rich_data, config, allow_sample=args.allow_sample)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    backend_path = args.out_dir / args.backend_json
    seed_path = args.out_dir / args.seed_sql
    report_path = args.out_dir / args.report
    write_json(backend_path, backend_data)
    seed_path.write_text(export_seed(backend_data, str(args.input)), encoding="utf-8")
    write_json(report_path, report)

    print(f"verdict={report['verdict']}")
    print(f"backendJson={backend_path}")
    print(f"seedSql={seed_path}")
    print(f"report={report_path}")
    print(f"questionBankRows={report['questionBankRows']}")
    print(f"answerKeyRows={report['answerKeyRows']}")
    if report["issues"]:
        print("issues:")
        for issue in report["issues"][:20]:
            print(f"- {issue}")
        if len(report["issues"]) > 20:
            print(f"- ... {len(report['issues']) - 20} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
