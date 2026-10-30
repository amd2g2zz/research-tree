"""Track B governed evaluation contract tests (#468, senior-user-ux-v2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation" / "harness"))

from run_v2_evaluation import (  # noqa: E402
    run_governed_evaluation,
)


@pytest.fixture(scope="module")
def receipt(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("v2-trackb") / "workspace"
    return run_governed_evaluation(workspace, scenarios=("interruption",), hosts=("codex",))


@pytest.fixture(scope="module")
def ledger(tmp_path_factory):
    from research_tree.run_ledger import RunLedger

    workspace = tmp_path_factory.mktemp("v2-trackb-ledger") / "workspace"
    run_governed_evaluation(workspace, scenarios=("interruption",), hosts=("codex",))
    return RunLedger(workspace)
