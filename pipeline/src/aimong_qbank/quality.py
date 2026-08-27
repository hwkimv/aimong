"""Quality audit: review candidates that never block the pipeline.

These checks describe questions a human may want to look at. They are
deliberately advisory: a warning here can be wrong, and demoting a hard
contract rule into this layer to make a run pass would defeat the point of
having a contract at all.
"""

from __future__ import annotations

import collections
import difflib
import re
from typing import Any

Warning_ = str

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s가-힣]")


def normalize_text(text: str) -> str:
    """Normalization used for duplicate detection only."""
    lowered = _PUNCTUATION.sub(" ", str(text).lower())
    return _WHITESPACE.sub(" ", lowered).strip()


def audit(questions: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    """Return warnings grouped by check, plus a flat list."""
    rules = contract["quality"]
    grouped: dict[str, list[Warning_]] = collections.defaultdict(list)

    _audit_tag_count(questions, rules, grouped)
    _audit_exact_duplicates(questions, grouped)
    _audit_similar_prompts(questions, rules, grouped)
    _audit_absolute_words(questions, rules, grouped)
    _audit_answer_length_bias(questions, grouped)
    _audit_duplicate_options(questions, grouped)

    flat = [warning for check in sorted(grouped) for warning in grouped[check]]
    return {
        "warningCount": len(flat),
        "byCheck": {check: len(items) for check, items in sorted(grouped.items())},
        "warnings": flat,
    }


def _audit_tag_count(questions, rules, grouped) -> None:
    limit = rules["maxContentTagsPerQuestion"]
    for question in questions:
        tags = question.get("contentTags") or []
        if isinstance(tags, list) and len(tags) > limit:
            grouped["contentTagCount"].append(
                f"{question.get('externalId')}: {len(tags)} contentTags exceeds the review limit of {limit}"
            )


def _audit_exact_duplicates(questions, grouped) -> None:
    by_prompt: dict[str, list[str]] = collections.defaultdict(list)
    for question in questions:
        prompt = normalize_text(question.get("question", ""))
        if prompt:
            by_prompt[prompt].append(question.get("externalId"))
    for prompt, ids in sorted(by_prompt.items()):
        if len(ids) > 1:
            grouped["duplicatePrompt"].append(f"identical prompt shared by {', '.join(sorted(ids))}")


def _audit_similar_prompts(questions, rules, grouped) -> None:
    """Near-duplicate prompts, compared within a mission to keep this tractable."""
    threshold = rules["duplicatePromptSimilarityThreshold"]
    by_mission: dict[Any, list[tuple[str, str]]] = collections.defaultdict(list)
    for question in questions:
        by_mission[question.get("missionCode")].append(
            (question.get("externalId"), normalize_text(question.get("question", "")))
        )
    for mission_code in sorted(by_mission, key=str):
        items = by_mission[mission_code]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                left_id, left = items[i]
                right_id, right = items[j]
                if not left or not right or left == right:
                    continue
                ratio = difflib.SequenceMatcher(None, left, right).ratio()
                if ratio >= threshold:
                    grouped["similarPrompt"].append(
                        f"{left_id} and {right_id} are {ratio:.3f} similar within {mission_code}"
                    )


def _audit_absolute_words(questions, rules, grouped) -> None:
    """Absolute wording often makes an option obviously wrong."""
    words = rules["absoluteWordList"]
    for question in questions:
        options = question.get("options")
        if not isinstance(options, list):
            continue
        for index, option in enumerate(options):
            if not isinstance(option, str):
                continue
            hit = next((word for word in words if word in option), None)
            if hit is not None and index != _answer_index(question):
                grouped["absoluteWording"].append(
                    f"{question.get('externalId')}: distractor {index} uses absolute wording {hit!r}"
                )


def _audit_answer_length_bias(questions, grouped) -> None:
    """A correct option that is always the longest is a guessable pattern."""
    for question in questions:
        options = question.get("options")
        answer_index = _answer_index(question)
        if not isinstance(options, list) or answer_index is None or not options:
            continue
        if not all(isinstance(option, str) for option in options):
            continue
        lengths = [len(option) for option in options]
        correct = lengths[answer_index] if 0 <= answer_index < len(lengths) else None
        if correct is None:
            continue
        others = [length for i, length in enumerate(lengths) if i != answer_index]
        if others and correct > max(others) * 1.8:
            grouped["answerLengthBias"].append(
                f"{question.get('externalId')}: correct option is {correct} chars vs longest distractor {max(others)}"
            )


def _audit_duplicate_options(questions, grouped) -> None:
    for question in questions:
        options = question.get("options")
        if not isinstance(options, list):
            continue
        normalized = [normalize_text(option) for option in options if isinstance(option, str)]
        repeated = sorted({value for value, count in collections.Counter(normalized).items() if count > 1 and value})
        for value in repeated:
            grouped["duplicateOption"].append(f"{question.get('externalId')}: option {value!r} appears more than once")


def _answer_index(question: dict[str, Any]) -> int | None:
    answer = question.get("answer")
    if isinstance(answer, bool):
        return None
    if isinstance(answer, int):
        return answer
    if isinstance(answer, list) and len(answer) == 1 and isinstance(answer[0], int):
        return answer[0]
    return None
