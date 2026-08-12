from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


def api():
    from research_tree import Alpha1MigrationError, Alpha1MigrationService

    return Alpha1MigrationError, Alpha1MigrationService


def test_inventory_and_projection_are_deterministic_and_read_only(tmp_path: Path) -> None:
    _, Alpha1MigrationService = api()
    native = tmp_path / ".research-tree-native" / "run-1"
    native.mkdir(parents=True)
    (native / "state.json").write_text('{"complete": true}', encoding="utf-8")
    hermes = tmp_path / ".research-tree-hermes"
    hermes.mkdir()
    (hermes / "events.jsonl").write_text('{"status":"complete"}\n', encoding="utf-8")

    service = Alpha1MigrationService(tmp_path)
    first = service.inventory()
    second = service.inventory()
    projection = service.write_compatibility_projection()

    assert first == second
    assert first.fingerprint == projection["inventory_fingerprint"]
    assert {item.surface for item in first.items} == {"native_checkpoint", "hermes_checkpoint"}
    assert all(item.completion_authority == "none" for item in first.items)
    assert projection["mode"] == "read_only"
    assert not (native / "migration.json").exists()
    assert not (hermes / "migration.json").exists()


def test_cutover_requires_passed_registered_release_gate(tmp_path: Path) -> None:
    Alpha1MigrationError, Alpha1MigrationService = api()
    service = Alpha1MigrationService(tmp_path)

    with pytest.raises(Alpha1MigrationError, match="release gate"):
        service.cut_over({"registered": True, "status": "fail"})

    result = service.cut_over({"registered": True, "status": "pass", "manifest_id": "candidate-1"})

    assert result["legacy_completion_writes"] == "retired"
    assert result["completion_authority"] == "coordinator_only"
    assert result["release_manifest_id"] == "candidate-1"
    assert service.rollback() == {"cutover": "disabled", "legacy_material": "retained_read_only"}


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ({"schema_version": 2}, "unsupported_schema_version"),
        ({"schema_version": 1, "host": "other"}, "stale_host_package_state"),
        ({"schema_version": 1, "host": "hermes", "duplicate_artifacts": ["a", "a"]}, "duplicate_artifacts"),
    ],
)
def test_host_state_diagnostics_are_deterministic_and_non_authoritative(
    tmp_path: Path, state: dict[str, object], code: str
) -> None:
    _, Alpha1MigrationService = api()
    path = tmp_path / ".research-tree-hermes" / "state.json"
    path.parent.mkdir()
    path.write_text(json.dumps(state), encoding="utf-8")

    inventory = Alpha1MigrationService(tmp_path).inventory()

    item = next(entry for entry in inventory.items if entry.surface == "hermes_checkpoint")
    assert item.diagnostic_code == code
    assert item.completion_authority == "none"


def test_malformed_host_state_has_no_partial_writable_authority(tmp_path: Path) -> None:
    _, Alpha1MigrationService = api()
    path = tmp_path / ".research-tree-native" / "run-1" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    result = Alpha1MigrationService(tmp_path).migrate(dry_run=False)

    assert result["disposition"] == "diagnostic_only"
    assert result["completion_authority"] == "coordinator_only"
    assert result["diagnostics"] == ["partial_or_corrupt_store"]
    assert not (tmp_path / ".research-tree-native" / "run-1" / "state.json").with_name("migration.json").exists()


def test_migration_cli_exposes_inventory_without_legacy_writes(tmp_path: Path) -> None:
    command = [sys.executable, "-m", "research_tree.migration_cli", "--workspace", str(tmp_path), "inventory"]

    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["completion_authority"] == "coordinator_only"
