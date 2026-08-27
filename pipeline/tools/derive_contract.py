#!/usr/bin/env python3
"""Derive the dataset hard contract from the canonical question bank.

The contract is not simply "whatever the data happens to contain". Every
structural quota written here must also be *declared* by the dataset itself
(totalQuestionCount, questionsPerMission, difficultyQuotaPerMission, ...).
When a declaration and the observed data disagree, this tool fails instead of
silently recording the observed value, so a stale declaration can never be
laundered into a contract.

Values that the dataset does not declare as a quota (the global type counts)
are recorded separately as a drift fingerprint, not as a designed quota.

Usage:
    python3 tools/derive_contract.py            # write contracts/dataset-contract.json
    python3 tools/derive_contract.py --check    # fail if the file is stale
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
DATASET = PIPELINE_ROOT / "data" / "question-bank-1056.json"
CONTRACT = PIPELINE_ROOT / "contracts" / "dataset-contract.json"

CONTRACT_VERSION = "1.0"


def fail(message: str) -> None:
    print(f"contract derivation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def check(label: str, declared, observed) -> None:
    """A quota only enters the contract when declaration and data agree."""
    if declared != observed:
        fail(f"{label}: dataset declares {declared!r} but data contains {observed!r}")


def derive(bank: dict) -> dict:
    questions = bank["questions"]
    missions = bank["missions"]

    per_mission = collections.Counter(q["missionCode"] for q in questions)
    observed_per_mission = sorted(set(per_mission.values()))

    check("totalQuestionCount", bank["totalQuestionCount"], len(questions))
    check("totalMissionCount", bank["totalMissionCount"], len(missions))
    check("questionsPerMission", [bank["questionsPerMission"]], observed_per_mission)

    # difficulty quota: declared per mission, must hold for every mission
    declared_difficulty = bank["difficultyQuotaPerMission"]
    by_mission_difficulty = collections.defaultdict(collections.Counter)
    for q in questions:
        by_mission_difficulty[q["missionCode"]][q["difficulty"]] += 1
    for code, counter in by_mission_difficulty.items():
        check(f"difficultyQuotaPerMission[{code}]", declared_difficulty, dict(counter))

    # pack sizes: declared indirectly via packsPerMission + actualPackTypeDistribution totals
    declared_pack_totals = {
        pack: sum(v for k, v in types.items() if k != "note")
        for pack, types in bank["actualPackTypeDistribution"].items()
    }
    by_mission_pack = collections.defaultdict(collections.Counter)
    for q in questions:
        by_mission_pack[q["missionCode"]][f"P{q['packNo']}"] += 1
    for code, counter in by_mission_pack.items():
        check(f"packSizePerMission[{code}]", declared_pack_totals, dict(counter))
    check("packsPerMission", bank["packsPerMission"], len(declared_pack_totals))

    # Global type counts are NOT a declared quota. The dataset's
    # actualPackTypeDistribution claims a per-pack type split that the data
    # contradicts, so type is recorded only as an observed drift fingerprint.
    type_counts = dict(sorted(collections.Counter(q["type"] for q in questions).items()))

    tags = sorted({t for q in questions for t in q["contentTags"]})
    mission_codes = sorted(m["missionCode"] for m in missions)

    return {
        "contractVersion": CONTRACT_VERSION,
        "canonicalDataset": "data/question-bank-1056.json",
        "provenance": {
            "generationVersion": bank["generationVersion"],
            "supersedes": {
                "previousQuestionCount": bank["highExpansion"]["previousQuestionCount"],
                "addedQuestionCount": bank["highExpansion"]["addedQuestionCount"]
                if "addedQuestionCount" in bank["highExpansion"]
                else bank["highExpansion"]["addedHighQuestionCount"],
                "addedPerMission": bank["highExpansion"]["addedPerMission"],
                "externalIdRangePerMission": bank["highExpansion"]["externalIdRangePerMission"],
                "note": (
                    "960 was the earlier generation plan. The dataset records a deliberate "
                    "expansion of +96 HIGH questions (6 per mission, P6-11..P6-16) to 1056, "
                    "so 1056 is the canonical size and config/mission-config.json is stale."
                ),
            },
        },
        "structure": {
            "totalQuestions": len(questions),
            "totalMissions": len(missions),
            "questionsPerMission": bank["questionsPerMission"],
            "packsPerMission": bank["packsPerMission"],
            "packSizePerMission": declared_pack_totals,
            "difficultyPerMission": declared_difficulty,
            "missionCodes": mission_codes,
        },
        "fingerprint": {
            "note": (
                "Observed global counts, recorded as a regression guard against silent "
                "data drift. These are not design quotas: the dataset declares a per-pack "
                "type split in actualPackTypeDistribution that the data does not satisfy, "
                "so per-pack type is deliberately not enforced."
            ),
            "typeCounts": type_counts,
        },
        "enums": {
            "type": ["OX", "MULTIPLE", "FILL", "SITUATION"],
            "difficulty": ["LOW", "MEDIUM", "HIGH"],
            "sourceType": ["STATIC", "GPT"],
            "generationPhase": ["PREGENERATED", "RUNTIME"],
            "contentTags": tags,
        },
        "fields": {
            "requiredNonEmptyStrings": [
                "externalId",
                "missionCode",
                "type",
                "difficulty",
                "question",
                "explanation",
                "curriculumRef",
            ],
            "externalIdPattern": r"^S\d{4}-P([1-6])-\d{2}$",
        },
        "typeShapes": {
            "OX": {"options": "null", "answer": "bool"},
            "MULTIPLE": {"options": "list[4]", "answer": "index"},
            "SITUATION": {"options": "list[4]", "answer": "index"},
            "FILL": {"options": "list[4]", "answer": "index-list"},
        },
        "quality": {
            "maxContentTagsPerQuestion": 3,
            "duplicatePromptSimilarityThreshold": 0.94,
            "absoluteWordList": ["항상", "절대", "무조건", "모든", "반드시"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed contract is stale")
    args = parser.parse_args()

    bank = json.loads(DATASET.read_text(encoding="utf-8"))
    contract = derive(bank)
    rendered = json.dumps(contract, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not CONTRACT.exists():
            fail(f"{CONTRACT} does not exist")
        if CONTRACT.read_text(encoding="utf-8") != rendered:
            fail(f"{CONTRACT} is stale; re-run tools/derive_contract.py")
        print(f"contract up to date: {CONTRACT.relative_to(PIPELINE_ROOT)}")
        return 0

    CONTRACT.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT.write_text(rendered, encoding="utf-8")
    print(f"wrote {CONTRACT.relative_to(PIPELINE_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
