"""Render the backend payload as JSON and as seed SQL.

The SQL targets the schema in backend/src/main/resources/db/migration:
public.missions, public.mission_sets, public.question_bank and
private.question_answer_keys. It is written to be re-runnable, so reseeding an
existing database updates rows instead of failing on conflicts.
"""

from __future__ import annotations

import json
from typing import Any

from .adapter import ADAPTER_VERSION, mission_sort_key


def sql_string(value: Any) -> str:
    """Dollar-quote text so Korean quotes and backslashes survive unescaped."""
    if value is None:
        return "NULL"
    text = str(value)
    tag = "$aimong$"
    if tag in text:
        tag = "$aimong_sql$"
    while tag in text:
        tag = f"$aimong_{len(tag)}$"
    return f"{tag}{text}{tag}"


def sql_jsonb(value: Any) -> str:
    return f"{sql_string(json.dumps(value, ensure_ascii=False, separators=(',', ':')))}::jsonb"


def render_json(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def render_sql(payload: dict[str, Any], source_name: str) -> str:
    mission_rows = [
        "("
        f"'{mission['missionId']}',"
        f"{int(mission['stage'])},"
        f"{sql_string(mission['missionTitle'])},"
        f"{sql_string(mission['missionCode'])},"
        f"{sql_string(mission.get('missionSummary'))},"
        "NULL,"
        "TRUE"
        ")"
        for mission in sorted(payload["missions"], key=mission_sort_key)
    ]

    set_rows = [
        "("
        f"{sql_string(row['setId'])},"
        f"'{row['missionId']}',"
        f"{sql_string(row['missionCode'])},"
        f"{int(row['starLevel'])},"
        f"{int(row['variantNo'])},"
        f"{int(row['stage'])},"
        f"{sql_string(row['title'])},"
        f"{sql_string(row['description'])},"
        f"{int(row['questionCount'])},"
        f"{int(row['displayOrder'])},"
        "TRUE"
        ")"
        for row in payload["missionSets"]
    ]

    question_rows = []
    answer_rows = []
    for question in payload["questions"]:
        question_rows.append(
            "("
            f"'{question['id']}',"
            f"'{question['missionId']}',"
            f"{sql_string(question['setId'])},"
            f"{sql_string(question['type'])}::question_type_enum,"
            f"{sql_string(question['difficulty'])}::question_difficulty_enum,"
            f"{sql_string(question['question'])},"
            f"{sql_jsonb(question['options'])},"
            f"{sql_jsonb(question['contentTags'])},"
            f"{sql_string(question['curriculumRef'])},"
            f"{sql_string(question['sourceType'])}::question_source_enum,"
            f"{sql_string(question['generationPhase'])}::question_generation_phase_enum,"
            f"{int(question['packNo'])},"
            "'ACTIVE'::question_pool_status_enum,"
            "NOW(),"
            "TRUE"
            ")"
        )
        answer_rows.append(
            "("
            f"'{question['id']}',"
            f"{sql_jsonb(question['answerPayload'])},"
            f"{sql_string(question['explanation'])},"
            "NOW()"
            ")"
        )

    mission_codes = [mission["missionCode"] for mission in payload["missions"]]
    set_ids = [row["setId"] for row in payload["missionSets"]]

    return "\n".join(
        [
            "-- AImong question-bank seed SQL",
            f"-- Adapter: {ADAPTER_VERSION}, contract: {payload['contractVersion']}",
            f"-- Source: {source_name}",
            f"-- missions: {len(mission_rows)}",
            f"-- mission_sets: {len(set_rows)}",
            f"-- question_bank: {len(question_rows)}",
            f"-- question_answer_keys: {len(answer_rows)}",
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
            "  is_active = TRUE;",
            "",
            "UPDATE public.missions SET is_active = FALSE",
            "WHERE mission_code NOT IN (" + ", ".join(sql_string(code) for code in mission_codes) + ");",
            "",
            "INSERT INTO public.mission_sets (",
            "  set_id, mission_id, mission_code, star_level, variant_no, stage,",
            "  title, description, question_count, display_order, is_active",
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
            "UPDATE public.mission_sets SET is_active = FALSE",
            "WHERE set_id NOT IN (" + ", ".join(sql_string(value) for value in set_ids) + ");",
            "",
            "INSERT INTO public.question_bank (",
            "  id, mission_id, set_id, question_type, difficulty, prompt, options, content_tags,",
            "  curriculum_ref, source_type, generation_phase, pack_no, question_pool_status, created_at, is_active",
            ")",
            "VALUES",
            ",\n".join(question_rows),
            "ON CONFLICT (id) DO UPDATE SET",
            "  mission_id = EXCLUDED.mission_id,",
            "  set_id = EXCLUDED.set_id,",
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
    )
