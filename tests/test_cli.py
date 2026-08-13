from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from research_tree import cli


ROOT = Path(__file__).resolve().parents[1]
RETIRED_COMMANDS = (
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
)


@pytest.mark.parametrize("command", RETIRED_COMMANDS)
def test_retired_cli_commands_are_unparseable_without_creating_a_store(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "retired-store"

    with pytest.raises(SystemExit) as exit_status:
        cli.main([command, "--store", str(store)])

    captured = capsys.readouterr()
    assert exit_status.value.code == 2
    assert command in captured.err
    assert "authority_blocked" not in captured.err
    assert "research-tree-migrate" not in captured.err
    assert captured.out == ""
    assert not store.exists()


def test_cli_help_does_not_discover_retired_commands() -> None:
    help_text = cli.build_parser().format_help()

    assert "canonical" in help_text.lower()
    for command in RETIRED_COMMANDS:
        assert command not in help_text


def test_migration_console_surface_and_public_exports_are_removed() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "research-tree-migrate" not in metadata["project"]["scripts"]
    assert not (ROOT / "src" / "research_tree" / "migration.py").exists()
    assert not (ROOT / "src" / "research_tree" / "migration_cli.py").exists()
    assert not hasattr(__import__("research_tree"), "Alpha1MigrationService")
