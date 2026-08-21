from __future__ import annotations

import importlib.util
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


def test_readme_and_cli_help_do_not_advertise_retired_runtime_scope() -> None:
    readme = Path(__file__).parents[1] / "README.md"
    content = readme.read_text(encoding="utf-8")

    assert "uv sync" in content
    assert "Python API for composed workflow services" in content
    for retired in (
        "create-round",
        "show-round",
        "tree-init",
        "tree-init-alignment",
        "tree-next",
        "tree-ingest",
        "tree-recover",
        "tree-deliver",
        "profile-inspect",
        "profile-correct",
        "profile-reset",
        "profile-delete",
        "research-tree-migrate",
    ):
        assert retired not in content

    help_output = _run_cli("--help")
    assert help_output.returncode == 0, help_output.stderr
    assert "canonical" in help_output.stdout.lower()
    assert "tree-recover" not in help_output.stdout


def test_legacy_application_facade_is_not_importable() -> None:
    assert importlib.util.find_spec("research_tree.application") is None


def test_legacy_feedback_service_is_not_published() -> None:
    import research_tree
    import research_tree.feedback as feedback

    assert not hasattr(research_tree, "FeedbackRoundService")
    assert not hasattr(feedback, "FeedbackRoundService")


def test_legacy_runstore_is_not_importable_or_published() -> None:
    import research_tree

    assert not hasattr(research_tree, "RunStore")
    assert importlib.util.find_spec("research_tree.storage") is None
