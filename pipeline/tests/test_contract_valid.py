"""The canonical dataset must satisfy the hard contract with zero errors."""

from __future__ import annotations

from aimong_qbank import contract as contract_module


def test_canonical_dataset_has_no_hard_contract_errors(canonical_bank, contract):
    errors = contract_module.validate(canonical_bank["questions"], contract)
    assert errors == []


def test_canonical_dataset_size_matches_contract(canonical_bank, contract):
    assert len(canonical_bank["questions"]) == contract["structure"]["totalQuestions"] == 1056
    assert len(canonical_bank["missions"]) == contract["structure"]["totalMissions"] == 16


def test_single_valid_question_passes(valid_question, contract):
    assert contract_module.validate_question(valid_question, contract) == []


def test_every_mission_meets_its_quota(canonical_bank, contract):
    assert contract_module.validate_structure(canonical_bank["questions"], contract) == []
