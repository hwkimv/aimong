"""Backend payload, JSON export and SQL export."""

from __future__ import annotations

import json

from aimong_qbank.adapter import build_payload, java_name_uuid, question_id, set_id, star_level, variant_no
from aimong_qbank.export import render_sql


def test_payload_covers_every_question(canonical_bank, contract):
    payload = build_payload(canonical_bank, contract)
    assert payload["questionCount"] == contract["structure"]["totalQuestions"]
    assert len(payload["questions"]) == contract["structure"]["totalQuestions"]


def test_java_name_uuid_matches_known_vector():
    # java.util.UUID.nameUUIDFromBytes("test".getBytes(UTF_8))
    assert java_name_uuid("test") == "098f6bcd-4621-3373-8ade-4e832627b4f6"


def test_question_ids_are_unique_and_deterministic(canonical_bank, contract):
    payload = build_payload(canonical_bank, contract)
    ids = [q["id"] for q in payload["questions"]]
    assert len(set(ids)) == len(ids), "derived UUIDs must not collide"
    again = build_payload(canonical_bank, contract)
    assert [q["id"] for q in again["questions"]] == ids


def test_every_question_is_bound_to_a_mission_set(canonical_bank, contract):
    """Questions exported without a set_id are invisible to set-based serving."""
    payload = build_payload(canonical_bank, contract)
    assert all(q["setId"] for q in payload["questions"])
    declared = {row["setId"] for row in payload["missionSets"]}
    used = {q["setId"] for q in payload["questions"]}
    assert used <= declared


def test_every_mission_set_has_enough_questions_to_serve(canonical_bank, contract):
    """The backend serves 10 questions per set and fails the attempt below that."""
    payload = build_payload(canonical_bank, contract)
    pool: dict[str, int] = {}
    for question in payload["questions"]:
        pool[question["setId"]] = pool.get(question["setId"], 0) + 1
    for row in payload["missionSets"]:
        assert pool.get(row["setId"], 0) >= row["questionCount"], row["setId"]


def test_mission_set_star_and_variant_are_unique_per_mission(canonical_bank, contract):
    payload = build_payload(canonical_bank, contract)
    seen = set()
    for row in payload["missionSets"]:
        key = (row["missionCode"], row["starLevel"], row["variantNo"])
        assert key not in seen, f"uq_mission_sets_mission_star_variant would reject {key}"
        seen.add(key)


def test_set_id_mapping():
    assert set_id("S0101", 3) == "S0101-L3"
    assert [star_level(p) for p in range(1, 7)] == [1, 1, 2, 2, 3, 3]
    assert [variant_no(p) for p in range(1, 7)] == [1, 2, 1, 2, 1, 2]


def test_json_export_is_serializable(canonical_bank, contract, tmp_path):
    payload = build_payload(canonical_bank, contract)
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["questionCount"] == payload["questionCount"]


def test_sql_export_shape(canonical_bank, contract):
    payload = build_payload(canonical_bank, contract)
    sql = render_sql(payload, "question-bank-1056.json")
    assert sql.startswith("-- AImong question-bank seed SQL")
    assert sql.count("BEGIN;") == 1
    assert sql.rstrip().endswith("COMMIT;")
    for table in (
        "public.missions",
        "public.mission_sets",
        "public.question_bank",
        "private.question_answer_keys",
    ):
        assert f"INSERT INTO {table}" in sql


def test_sql_export_is_rerunnable(canonical_bank, contract):
    """Reseeding an existing database must update rather than fail."""
    sql = render_sql(build_payload(canonical_bank, contract), "x.json")
    assert sql.count("ON CONFLICT") == 4


def test_sql_contains_no_null_set_id_for_questions(canonical_bank, contract):
    sql = render_sql(build_payload(canonical_bank, contract), "x.json")
    question_block = sql.split("INSERT INTO public.question_bank")[1].split("ON CONFLICT")[0]
    assert ",NULL," not in question_block


def test_question_id_is_stable_for_known_external_id():
    assert question_id("S0101-P1-01") == java_name_uuid("question:S0101-P1-01")
