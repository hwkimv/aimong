from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT / "src"))

from aimong_qbank.paths import canonical_dataset_path, load_contract  # noqa: E402


@pytest.fixture(scope="session")
def contract() -> dict:
    return load_contract()


@pytest.fixture(scope="session")
def canonical_bank(contract) -> dict:
    return json.loads(canonical_dataset_path(contract).read_text(encoding="utf-8"))


@pytest.fixture
def bank(canonical_bank) -> dict:
    """A mutable copy, so a test that breaks the data cannot leak into others."""
    return copy.deepcopy(canonical_bank)


@pytest.fixture
def valid_question(canonical_bank) -> dict:
    return copy.deepcopy(canonical_bank["questions"][0])


@pytest.fixture
def valid_multiple(canonical_bank) -> dict:
    return copy.deepcopy(next(q for q in canonical_bank["questions"] if q["type"] == "MULTIPLE"))


@pytest.fixture
def valid_fill(canonical_bank) -> dict:
    return copy.deepcopy(next(q for q in canonical_bank["questions"] if q["type"] == "FILL"))
