from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "research_tree", *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
    )


def test_documented_first_use_and_recovery_path(tmp_path: Path) -> None:
    root = tmp_path / "research-tree-demo"

    created = _run_cli(
        "create-round", "--store", str(root), "--round-id", "round-first"
    )
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["id"] == "round-first"

    recovered = _run_cli(
        "show-round", "--store", str(root), "--round-id", "round-first"
    )
    assert recovered.returncode == 0, recovered.stderr
    assert json.loads(recovered.stdout)["record"]["id"] == "round-first"


def test_readme_and_cli_help_make_runtime_scope_discoverable() -> None:
    readme = Path(__file__).parents[1] / "README.md"
    content = readme.read_text(encoding="utf-8")

    for expected in (
        "uv sync",
        "uv run python -m research_tree create-round",
        "uv run python -m research_tree show-round",
            "uv run python -m research_tree tree-init",
            "uv run python -m research_tree tree-init-alignment",
        "uv run python -m research_tree tree-next",
        "persisted recursive",
        "`research_tree` Python API",
    ):
        assert expected in content

    help_output = _run_cli("--help")
    assert help_output.returncode == 0, help_output.stderr
    assert "recursive research-tree state" in help_output.stdout.lower()
    assert "tree-recover" in help_output.stdout
