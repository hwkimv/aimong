"""One-command verification of the question bank.

    python3 -m aimong_qbank.cli verify

Runs contract validation, the quality audit and both exports in the order the
pipeline depends on, and reports the numbers from this run rather than from a
stored report. Hard contract errors fail the command; quality warnings do not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import contract as contract_module
from . import quality as quality_module
from .adapter import build_payload
from .export import render_sql
from .paths import (
    DEFAULT_OUT_DIR,
    canonical_dataset_path,
    load_contract,
    read_json,
    write_json,
)


def run_verify(
    dataset: Path | None = None,
    contract_path: Path | None = None,
    out_dir: Path | None = None,
    skip_export: bool = False,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    dataset_path = Path(dataset) if dataset else canonical_dataset_path(contract)
    bank = read_json(dataset_path)

    questions = bank.get("questions")
    if not isinstance(questions, list):
        return {
            "verdict": "FAIL",
            "dataset": str(dataset_path),
            "hardContractErrors": ["root.questions must be a list"],
            "quality": {"warningCount": 0, "byCheck": {}, "warnings": []},
            "artifacts": {},
        }

    errors = contract_module.validate(questions, contract)
    audit = quality_module.audit(questions, contract)

    result: dict[str, Any] = {
        "verdict": "FAIL" if errors else "PASS",
        "dataset": str(dataset_path),
        "contractVersion": contract["contractVersion"],
        "questionCount": len(questions),
        "missionCount": len(bank.get("missions", [])),
        "hardContractErrors": errors,
        "quality": audit,
        "artifacts": {},
    }

    if errors or skip_export:
        return result

    payload = build_payload(bank, contract)
    out = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    backend_json = out / "backend-compatible-question-bank.json"
    seed_sql = out / "question-bank-seed.sql"
    write_json(backend_json, payload)
    seed_sql.write_text(render_sql(payload, dataset_path.name), encoding="utf-8")

    result["artifacts"] = {
        "backendJson": str(backend_json),
        "seedSql": str(seed_sql),
        "questionBankRows": len(payload["questions"]),
        "answerKeyRows": len(payload["questions"]),
        "missionRows": len(payload["missions"]),
        "missionSetRows": len(payload["missionSets"]),
    }
    write_json(out / "verify-report.json", result)
    return result


def _print(result: dict[str, Any]) -> None:
    errors = result["hardContractErrors"]
    audit = result["quality"]
    print(result["verdict"])
    print()
    print("Dataset")
    print(f"- Questions: {result.get('questionCount', 0):,}")
    print(f"- Missions: {result.get('missionCount', 0)}")
    print(f"- Hard contract errors: {len(errors)}")
    print(f"- Quality warnings: {audit['warningCount']}")
    for check, count in audit["byCheck"].items():
        print(f"    {check}: {count}")

    if errors:
        print()
        print("Hard contract errors")
        for issue in errors[:20]:
            print(f"- {issue}")
        if len(errors) > 20:
            print(f"- ... {len(errors) - 20} more")
        return

    artifacts = result.get("artifacts") or {}
    if artifacts:
        print()
        print("Artifacts")
        print(f"- Backend JSON: {artifacts['backendJson']}")
        print(f"- Seed SQL: {artifacts['seedSql']}")
        print(f"- question_bank rows: {artifacts['questionBankRows']:,}")
        print(f"- question_answer_keys rows: {artifacts['answerKeyRows']:,}")
        print(f"- mission_sets rows: {artifacts['missionSetRows']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify"], nargs="?", default="verify")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--contract", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    result = run_verify(args.dataset, args.contract, args.out_dir, args.skip_export)
    _print(result)
    return 1 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
