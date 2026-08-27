"""Each hard contract rule must actually reject the data it claims to reject.

A validator that never fails is indistinguishable from no validator, so every
rule gets a test that breaks the data and asserts the specific complaint.
"""

from __future__ import annotations

import pytest

from aimong_qbank import contract as contract_module


def errors_for(question, contract):
    return contract_module.validate_question(question, contract)


def test_duplicate_external_id_is_rejected(bank, contract):
    bank["questions"][1]["externalId"] = bank["questions"][0]["externalId"]
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any("externalId duplicated" in error for error in errors)


def test_answer_index_above_range_is_rejected(valid_multiple, contract):
    valid_multiple["answer"] = len(valid_multiple["options"])
    assert any("outside options" in error for error in errors_for(valid_multiple, contract))


def test_negative_answer_index_is_rejected(valid_multiple, contract):
    valid_multiple["answer"] = -1
    assert any("outside options" in error for error in errors_for(valid_multiple, contract))


@pytest.mark.parametrize(
    "field", ["externalId", "missionCode", "type", "difficulty", "question", "explanation", "curriculumRef"]
)
def test_missing_required_field_is_rejected(valid_question, contract, field):
    valid_question[field] = ""
    assert any(field in error for error in errors_for(valid_question, contract))


def test_unknown_type_is_rejected(valid_question, contract):
    valid_question["type"] = "ESSAY"
    assert any("unsupported type" in error for error in errors_for(valid_question, contract))


def test_unknown_difficulty_is_rejected(valid_question, contract):
    valid_question["difficulty"] = "EXTREME"
    assert any("unsupported difficulty" in error for error in errors_for(valid_question, contract))


def test_unknown_content_tag_is_rejected(valid_question, contract):
    valid_question["contentTags"] = ["NOT_A_REAL_TAG"]
    assert any("unsupported contentTag" in error for error in errors_for(valid_question, contract))


def test_empty_content_tags_is_rejected(valid_question, contract):
    valid_question["contentTags"] = []
    assert any("contentTags must be a non-empty list" in error for error in errors_for(valid_question, contract))


def test_pack_out_of_range_is_rejected(valid_question, contract):
    valid_question["packNo"] = 9
    assert any("packNo" in error for error in errors_for(valid_question, contract))


def test_external_id_pack_must_match_pack_no(valid_question, contract):
    valid_question["packNo"] = 1 if valid_question["packNo"] != 1 else 2
    assert any("does not match packNo" in error for error in errors_for(valid_question, contract))


def test_unknown_mission_code_is_rejected(valid_question, contract):
    valid_question["missionCode"] = "S9999"
    assert any("unknown missionCode" in error for error in errors_for(valid_question, contract))


def test_wrong_option_count_is_rejected(valid_multiple, contract):
    valid_multiple["options"] = valid_multiple["options"][:3]
    assert any("exactly 4 choices" in error for error in errors_for(valid_multiple, contract))


def test_ox_with_options_is_rejected(valid_question, contract):
    assert valid_question["type"] == "OX"
    valid_question["options"] = ["a", "b", "c", "d"]
    assert any("OX options must be null or empty" in error for error in errors_for(valid_question, contract))


def test_ox_with_integer_answer_is_rejected(valid_question, contract):
    valid_question["answer"] = 1
    assert any("OX answer must be a boolean" in error for error in errors_for(valid_question, contract))


def test_multiple_with_boolean_answer_is_rejected(valid_multiple, contract):
    valid_multiple["answer"] = True
    assert any("0-based integer index" in error for error in errors_for(valid_multiple, contract))


def test_fill_with_scalar_answer_is_rejected(valid_fill, contract):
    valid_fill["answer"] = 0
    assert any("non-empty list" in error for error in errors_for(valid_fill, contract))


def test_fill_index_outside_options_is_rejected(valid_fill, contract):
    valid_fill["answer"] = [len(valid_fill["options"])]
    assert any("outside options" in error for error in errors_for(valid_fill, contract))


def test_missing_mission_questions_are_rejected(bank, contract):
    dropped = bank["questions"][0]["missionCode"]
    bank["questions"] = [q for q in bank["questions"] if q["missionCode"] != dropped]
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any(f"missionCode {dropped} has no questions" in error for error in errors)


def test_short_mission_is_rejected(bank, contract):
    target = bank["questions"][0]["missionCode"]
    index = next(i for i, q in enumerate(bank["questions"]) if q["missionCode"] == target)
    bank["questions"].pop(index)
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any(f"questionsPerMission[{target}]" in error for error in errors)


def test_total_count_mismatch_is_rejected(bank, contract):
    bank["questions"].pop()
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any("totalQuestions" in error for error in errors)


def test_type_drift_is_rejected(bank, contract):
    """Silently rewriting a question's type must not slip through."""
    target = next(q for q in bank["questions"] if q["type"] == "MULTIPLE")
    target["type"] = "SITUATION"
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any("typeCounts drifted" in error for error in errors)


def test_difficulty_quota_violation_is_rejected(bank, contract):
    target = next(q for q in bank["questions"] if q["difficulty"] == "LOW")
    target["difficulty"] = "HIGH"
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any("difficultyPerMission" in error for error in errors)


def test_pack_quota_violation_is_rejected(bank, contract):
    target = next(q for q in bank["questions"] if q["packNo"] == 1)
    target["packNo"] = 2
    errors = contract_module.validate_structure(bank["questions"], contract)
    assert any("packSizePerMission" in error for error in errors)
