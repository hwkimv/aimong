"""Quality warnings must stay advisory and must not gate the pipeline."""

from __future__ import annotations

from aimong_qbank import contract as contract_module
from aimong_qbank import quality as quality_module


def test_quality_audit_runs_on_canonical_dataset(canonical_bank, contract):
    audit = quality_module.audit(canonical_bank["questions"], contract)
    assert audit["warningCount"] >= 0
    assert set(audit["byCheck"]) <= {
        "contentTagCount",
        "duplicatePrompt",
        "similarPrompt",
        "absoluteWording",
        "answerLengthBias",
        "duplicateOption",
    }


def test_quality_warnings_do_not_become_contract_errors(canonical_bank, contract):
    """A dataset with warnings still has to pass the hard contract."""
    audit = quality_module.audit(canonical_bank["questions"], contract)
    errors = contract_module.validate(canonical_bank["questions"], contract)
    assert audit["warningCount"] > 0
    assert errors == []


def test_too_many_tags_warns_but_does_not_fail(valid_question, contract):
    valid_question["contentTags"] = ["FACT", "SAFETY", "PRIVACY", "PROMPT"]
    audit = quality_module.audit([valid_question], contract)
    assert any("contentTags" in warning for warning in audit["warnings"])
    assert contract_module.validate_question(valid_question, contract) == []


def test_identical_prompts_are_flagged(valid_question, contract):
    twin = dict(valid_question)
    twin["externalId"] = "S0101-P1-02"
    audit = quality_module.audit([valid_question, twin], contract)
    assert any("identical prompt" in warning for warning in audit["warnings"])


def test_duplicate_option_is_flagged(valid_multiple, contract):
    valid_multiple["options"][1] = valid_multiple["options"][0]
    audit = quality_module.audit([valid_multiple], contract)
    assert any("appears more than once" in warning for warning in audit["warnings"])


def test_normalize_text_ignores_punctuation_and_case():
    assert quality_module.normalize_text("AI, 는  좋아요!") == quality_module.normalize_text("ai 는 좋아요")
