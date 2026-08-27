"""Boundary cases: first/last valid index, Unicode, quoting, empty and long text."""

from __future__ import annotations

import pytest

from aimong_qbank import contract as contract_module
from aimong_qbank.adapter import answer_payload
from aimong_qbank.export import sql_string


def test_first_answer_index_is_accepted(valid_multiple, contract):
    valid_multiple["answer"] = 0
    assert contract_module.validate_question(valid_multiple, contract) == []


def test_last_answer_index_is_accepted(valid_multiple, contract):
    valid_multiple["answer"] = len(valid_multiple["options"]) - 1
    assert contract_module.validate_question(valid_multiple, contract) == []


def test_fill_first_and_last_index_are_accepted(valid_fill, contract):
    for index in (0, len(valid_fill["options"]) - 1):
        valid_fill["answer"] = [index]
        assert contract_module.validate_question(valid_fill, contract) == []


def test_answer_payload_shifts_to_one_based(valid_multiple, valid_fill):
    valid_multiple["answer"] = 0
    assert answer_payload(valid_multiple) == 1
    valid_multiple["answer"] = 3
    assert answer_payload(valid_multiple) == 4
    valid_fill["answer"] = [0, 3]
    assert answer_payload(valid_fill) == [1, 4]


def test_ox_answer_payload_stays_boolean(valid_question):
    valid_question["answer"] = True
    assert answer_payload(valid_question) is True
    valid_question["answer"] = False
    assert answer_payload(valid_question) is False


def test_whitespace_only_string_counts_as_empty(valid_question, contract):
    valid_question["question"] = "   \n\t "
    assert any("question" in error for error in contract_module.validate_question(valid_question, contract))


def test_blank_option_is_rejected(valid_multiple, contract):
    valid_multiple["options"][2] = "  "
    errors = contract_module.validate_question(valid_multiple, contract)
    assert any("non-empty strings" in error for error in errors)


def test_long_prompt_is_accepted(valid_question, contract):
    valid_question["question"] = "가" * 5000
    assert contract_module.validate_question(valid_question, contract) == []


@pytest.mark.parametrize(
    "text",
    [
        "한글 문장입니다",
        "quote ' inside",
        'double " quote',
        "back\\slash",
        "semi; colon -- comment",
        "emoji 🙂 and 漢字",
        "$aimong$ tag collision",
        "'; DROP TABLE public.question_bank; --",
    ],
)
def test_sql_string_round_trips_special_text(text):
    rendered = sql_string(text)
    assert rendered.startswith("$")
    tag = rendered[: rendered.index("$", 1) + 1]
    assert rendered == f"{tag}{text}{tag}"
    assert tag not in text


def test_sql_string_renders_none_as_null():
    assert sql_string(None) == "NULL"
