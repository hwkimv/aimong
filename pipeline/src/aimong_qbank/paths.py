"""Path resolution anchored to the pipeline root.

Every path is derived from this module's location, so the commands behave the
same whether they are run from the repository root, from pipeline/, or from CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE_ROOT.parent

CONTRACT_PATH = PIPELINE_ROOT / "contracts" / "dataset-contract.json"
DATA_DIR = PIPELINE_ROOT / "data"
DEFAULT_OUT_DIR = Path(os.environ.get("AIMONG_OUT_DIR") or (PIPELINE_ROOT / "out"))

BACKEND_MIGRATIONS = REPO_ROOT / "backend" / "src" / "main" / "resources" / "db" / "migration"


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_contract(path: Path | None = None) -> dict[str, Any]:
    return read_json(path or CONTRACT_PATH)


def canonical_dataset_path(contract: dict[str, Any]) -> Path:
    return PIPELINE_ROOT / contract["canonicalDataset"]
