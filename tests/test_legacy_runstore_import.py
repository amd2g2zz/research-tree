from __future__ import annotations

import json
from pathlib import Path

from research_tree import ArtifactRef, LegacyRunStoreImporter, RunLedger, RunStore


def test_import_reconstructs_historical_lineage_and_is_idempotent(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy = RunStore(legacy_root)
    legacy.create_round("round-1")
    first = legacy.append_artifact("round-1", "brief", "working-brief", {"goal": "old"})
    legacy.append_artifact("round-1", "brief", "validation-result", {"status": "passed"}, parent_refs=(ArtifactRef("round-1", "brief", first.revision),))
    ledger = RunLedger(tmp_path / "alpha2")
    importer = LegacyRunStoreImporter(legacy_root, ledger)

    result = importer.import_round("round-1")
    repeated = importer.import_round("round-1")
    snapshot = ledger.load_run("round-1")

    assert result.receipt.disposition == "imported"
    assert repeated.receipt.disposition == "already_imported"
    assert len(snapshot.artifacts) == 2
    assert all(artifact.kind.startswith("legacy-") for artifact in snapshot.artifacts)
    assert all(artifact.payload["legacy_disposition"] == "legacy_unverified" for artifact in snapshot.artifacts)
    assert len(snapshot.artifacts) == len({(artifact.id, artifact.revision) for artifact in snapshot.artifacts})


def test_malformed_round_is_quarantined_without_creating_a_run(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy = RunStore(legacy_root)
    legacy.create_round("round-1")
    legacy.append_artifact("round-1", "brief", "working-brief", {"goal": "old"})
    artifact_path = legacy_root / "rounds" / "round-1" / "artifacts" / "brief" / "000001.json"
    artifact_path.write_text("{malformed", encoding="utf-8")
    ledger = RunLedger(tmp_path / "alpha2")

    result = LegacyRunStoreImporter(legacy_root, ledger).import_round("round-1")

    assert result.receipt.disposition == "quarantined"
    assert result.receipt.run_id is None
    assert not (tmp_path / "alpha2" / ".research-tree" / "run-ledger.sqlite3").exists() or ledger.get_import_receipt(result.receipt.source_digest) is not None


def test_run_id_collision_is_recorded_without_mutating_existing_run(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy = RunStore(legacy_root)
    legacy.create_round("round-1")
    legacy.append_artifact("round-1", "brief", "working-brief", {"goal": "old"})
    ledger = RunLedger(tmp_path / "alpha2")
    importer = LegacyRunStoreImporter(legacy_root, ledger)
    assert importer.import_round("round-1").receipt.disposition == "imported"

    legacy.append_artifact("round-1", "new", "finding", {"value": 2})
    result = importer.import_round("round-1")

    assert result.receipt.disposition == "conflict"
    assert len(ledger.load_run("round-1").artifacts) == 1


def test_dry_run_does_not_write_canonical_artifacts(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy = RunStore(legacy_root)
    legacy.create_round("round-1")
    legacy.append_artifact("round-1", "brief", "working-brief", {"goal": "old"})
    ledger = RunLedger(tmp_path / "alpha2")

    result = LegacyRunStoreImporter(legacy_root, ledger).import_round("round-1", dry_run=True)

    assert result.receipt.disposition == "legacy_unverified"
    assert result.snapshot is not None
    assert ledger.get_import_receipt(result.receipt.source_digest) is None
