"""Hard contract validation.

A hard contract violation means the dataset cannot be trusted as backend data:
a required field is missing, an enum value is unknown, an identifier collides,
an answer points outside its options, or a declared structural quota does not
hold. Any violation fails the pipeline.

Quality concerns that a human should review, but that do not block loading the
data, live in quality.py and never produce errors here.
"""

from __future__ import annotations

import collections
import re
from typing import Any

Issue = str


class ContractViolation(Exception):
    """Raised when the pipeline is asked to export data that failed the contract."""


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_question(question: dict[str, Any], contract: dict[str, Any]) -> list[Issue]:
    """Field-level checks for a single question."""
    issues: list[Issue] = []
    enums = contract["enums"]
    fields = contract["fields"]

    external_id = question.get("externalId")
    prefix = external_id if _nonempty_string(external_id) else "<missing externalId>"

    for field in fields["requiredNonEmptyStrings"]:
        if not _nonempty_string(question.get(field)):
            issues.append(f"{prefix}: missing or empty {field}")

    pack_no = question.get("packNo")
    if not isinstance(pack_no, int) or isinstance(pack_no, bool) or not 1 <= pack_no <= contract["structure"]["packsPerMission"]:
        issues.append(f"{prefix}: packNo must be an integer from 1 to {contract['structure']['packsPerMission']}")
        pack_no = None

    if _nonempty_string(external_id):
        match = re.match(fields["externalIdPattern"], external_id)
        if not match:
            issues.append(f"{prefix}: externalId must match {fields['externalIdPattern']}")
        elif pack_no is not None and int(match.group(1)) != pack_no:
            issues.append(f"{prefix}: externalId pack {match.group(1)} does not match packNo {pack_no}")

    if question.get("missionCode") not in contract["structure"]["missionCodes"]:
        issues.append(f"{prefix}: unknown missionCode {question.get('missionCode')!r}")

    question_type = question.get("type")
    for field, allowed in (
        ("type", enums["type"]),
        ("difficulty", enums["difficulty"]),
        ("sourceType", enums["sourceType"]),
        ("generationPhase", enums["generationPhase"]),
    ):
        if question.get(field) not in allowed:
            issues.append(f"{prefix}: unsupported {field} {question.get(field)!r}")

    tags = question.get("contentTags")
    if not isinstance(tags, list) or not tags:
        issues.append(f"{prefix}: contentTags must be a non-empty list")
    else:
        for tag in tags:
            if tag not in enums["contentTags"]:
                issues.append(f"{prefix}: unsupported contentTag {tag!r}")

    issues.extend(_validate_shape(prefix, question_type, question.get("options"), question.get("answer")))
    return issues


def _validate_shape(prefix: str, question_type: Any, options: Any, answer: Any) -> list[Issue]:
    """Options/answer shape must match the question type, or the row cannot be graded."""
    issues: list[Issue] = []

    if question_type == "OX":
        if options not in (None, []):
            issues.append(f"{prefix}: OX options must be null or empty")
        if not isinstance(answer, bool):
            issues.append(f"{prefix}: OX answer must be a boolean")
        return issues

    if question_type in {"MULTIPLE", "SITUATION", "FILL"}:
        if not isinstance(options, list) or len(options) != 4:
            issues.append(f"{prefix}: {question_type} options must have exactly 4 choices")
            return issues
        if any(not _nonempty_string(option) for option in options):
            issues.append(f"{prefix}: {question_type} options must all be non-empty strings")

    if question_type in {"MULTIPLE", "SITUATION"}:
        if isinstance(answer, bool) or not isinstance(answer, int):
            issues.append(f"{prefix}: {question_type} answer must be a 0-based integer index")
        elif not 0 <= answer < len(options):
            issues.append(f"{prefix}: {question_type} answer index {answer} is outside options (0..{len(options) - 1})")
    elif question_type == "FILL":
        if not isinstance(answer, list) or not answer:
            issues.append(f"{prefix}: FILL answer must be a non-empty list of 0-based indexes")
        else:
            for item in answer:
                if isinstance(item, bool) or not isinstance(item, int):
                    issues.append(f"{prefix}: FILL answer entry {item!r} must be an integer index")
                elif not 0 <= item < len(options):
                    issues.append(f"{prefix}: FILL answer index {item} is outside options (0..{len(options) - 1})")

    return issues


def validate_structure(questions: list[dict[str, Any]], contract: dict[str, Any]) -> list[Issue]:
    """Dataset-level quotas declared by the contract."""
    issues: list[Issue] = []
    structure = contract["structure"]

    if len(questions) != structure["totalQuestions"]:
        issues.append(f"totalQuestions: expected {structure['totalQuestions']}, got {len(questions)}")

    ids = [q.get("externalId") for q in questions]
    duplicates = sorted({i for i, count in collections.Counter(ids).items() if count > 1 and i is not None})
    for duplicate in duplicates:
        issues.append(f"externalId duplicated: {duplicate}")

    per_mission = collections.Counter(q.get("missionCode") for q in questions)
    expected_codes = set(structure["missionCodes"])
    observed_codes = {code for code in per_mission if code in expected_codes}
    for missing in sorted(expected_codes - observed_codes):
        issues.append(f"missionCode {missing} has no questions")

    expected_per_mission = structure["questionsPerMission"]
    for code in sorted(expected_codes & observed_codes):
        if per_mission[code] != expected_per_mission:
            issues.append(f"questionsPerMission[{code}]: expected {expected_per_mission}, got {per_mission[code]}")

    by_mission_pack: dict[Any, collections.Counter] = collections.defaultdict(collections.Counter)
    by_mission_difficulty: dict[Any, collections.Counter] = collections.defaultdict(collections.Counter)
    for question in questions:
        code = question.get("missionCode")
        if code not in expected_codes:
            continue
        if isinstance(question.get("packNo"), int) and not isinstance(question.get("packNo"), bool):
            by_mission_pack[code][f"P{question['packNo']}"] += 1
        if question.get("difficulty") in contract["enums"]["difficulty"]:
            by_mission_difficulty[code][question["difficulty"]] += 1

    for code in sorted(expected_codes & observed_codes):
        observed_pack = dict(by_mission_pack[code])
        if observed_pack != structure["packSizePerMission"]:
            issues.append(f"packSizePerMission[{code}]: expected {structure['packSizePerMission']}, got {observed_pack}")
        observed_difficulty = dict(by_mission_difficulty[code])
        if observed_difficulty != structure["difficultyPerMission"]:
            issues.append(
                f"difficultyPerMission[{code}]: expected {structure['difficultyPerMission']}, got {observed_difficulty}"
            )

    observed_types = dict(sorted(collections.Counter(q.get("type") for q in questions).items()))
    expected_types = contract["fingerprint"]["typeCounts"]
    if observed_types != expected_types:
        issues.append(f"typeCounts drifted: expected {expected_types}, got {observed_types}")

    return issues


def validate(questions: list[dict[str, Any]], contract: dict[str, Any]) -> list[Issue]:
    """Full hard contract: every question, then the dataset as a whole."""
    issues: list[Issue] = []
    for question in questions:
        issues.extend(validate_question(question, contract))
    issues.extend(validate_structure(questions, contract))
    return issues
