"""End-to-end behaviour of the verify command."""

from __future__ import annotations

import json

from aimong_qbank.cli import run_verify


def test_verify_passes_on_canonical_dataset(tmp_path):
    result = run_verify(out_dir=tmp_path)
    assert result["verdict"] == "PASS"
    assert result["hardContractErrors"] == []
    assert result["questionCount"] == 1056


def test_verify_writes_both_artifacts(tmp_path):
    result = run_verify(out_dir=tmp_path)
    assert (tmp_path / "backend-compatible-question-bank.json").exists()
    assert (tmp_path / "question-bank-seed.sql").exists()
    assert result["artifacts"]["questionBankRows"] == 1056
    assert result["artifacts"]["missionSetRows"] == 96


def test_verify_fails_and_skips_export_on_broken_dataset(tmp_path, bank):
    """A failed contract must not leave artifacts behind for the DB step to use."""
    bank["questions"][1]["externalId"] = bank["questions"][0]["externalId"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "out"
    result = run_verify(dataset=broken, out_dir=out)

    assert result["verdict"] == "FAIL"
    assert any("externalId duplicated" in error for error in result["hardContractErrors"])
    assert not (out / "question-bank-seed.sql").exists()
