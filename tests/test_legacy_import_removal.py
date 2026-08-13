from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import research_tree


def test_legacy_import_authority_is_not_published_or_importable() -> None:
    retired_symbols = (
        "LegacyImportError",
        "LegacyImportReceipt",
        "LegacyImportResult",
        "LegacyRunStoreImporter",
    )

    assert all(not hasattr(research_tree, symbol) for symbol in retired_symbols)
    assert importlib.util.find_spec("research_tree.legacy_import") is None


def test_new_ledger_omits_legacy_import_receipts_and_preserves_canonical_tables(tmp_path: Path) -> None:
    from research_tree.run_ledger import RunLedger

    ledger = RunLedger(tmp_path)
    ledger.initialize()

    assert not hasattr(ledger, "record_import_receipt")
    assert not hasattr(ledger, "get_import_receipt")
    with sqlite3.connect(ledger.database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert "legacy_imports" not in tables
    assert {"runs", "artifacts", "events", "content_objects"} <= tables


def test_active_governance_registers_only_the_removal_slice() -> None:
    umbrella_root = Path(__file__).resolve().parents[1] / "openspec" / "changes" / "unify-research-runtime-alpha2"
    registry_root = umbrella_root / "registries"
    repository_root = umbrella_root.parents[2]
    execution = json.loads((registry_root / "task-execution-v1.json").read_text(encoding="utf-8"))
    verification = json.loads((registry_root / "task-verification-v1.json").read_text(encoding="utf-8"))
    issue_map = json.loads((registry_root / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    matrix = json.loads((registry_root / "delivery-matrix-v1.json").read_text(encoding="utf-8"))

    assert 34 not in {item["group"] for item in execution["groups"]}
    assert 34 not in {item["group"] for item in verification["groups"]}
    assert 13 not in {item["group"] for item in execution["groups"]}
    assert 13 not in {item["group"] for item in verification["groups"]}
    assert {item["group"] for item in execution["groups"]} >= {55}
    assert next(item for item in verification["groups"] if item["group"] == 55)["state"] == "verified"
    assert all("legacy-runstore-import" not in item["capabilities"] for item in issue_map["issues"])
    assert all(item["issue"] != 65 for item in issue_map["issues"])
    assert all(13 not in [item["primary_group"], *item["supporting_groups"]] for item in issue_map["issues"])
    assert all(item["capability"] != "legacy-runstore-import" for item in matrix["capability_rows"])

    retired_artifacts = (
        umbrella_root / "schemas" / "compatibility-matrix.md",
        registry_root / "legacy-field-map-v1.json",
    )
    assert all(not path.exists() for path in retired_artifacts)

    active_sources = (
        umbrella_root / "proposal.md",
        umbrella_root / "design.md",
        umbrella_root / "tasks.md",
        umbrella_root / "schemas" / "README.md",
        umbrella_root / "specs" / "durable-research-runtime" / "spec.md",
        umbrella_root / "specs" / "host-event-protocol" / "spec.md",
        umbrella_root / "specs" / "implementation-release-contract" / "spec.md",
        registry_root / "task-execution-v1.json",
        registry_root / "task-verification-v1.json",
        registry_root / "issue-execution-map-v1.json",
        registry_root / "delivery-matrix-v1.json",
        repository_root / "docs" / "adr" / "ADR-004-sqlite-and-content-addressed-storage.md",
    )
    retired_claims = (
        "compatibility-matrix.md",
        "legacy-field-map-v1.json",
        "tests/test_migration.py",
        "alpha2-migration-packaging",
        '"group": 13',
        '"issue": 65',
        "filesystem RunStore import",
        "idempotent legacy importer",
        "read-only compatibility projections",
        "route reads to legacy projection",
        "restore alpha1 reader",
        "Alpha1 RunStore rounds are imported idempotently",
        "Compatibility readers remain available",
    )
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_sources)

    assert all(claim not in active_text for claim in retired_claims)
    assert not (repository_root / "openspec" / "changes" / "import-alpha1-runstore").exists()
    assert (repository_root / "openspec" / "changes" / "archive" / "2026-08-13-import-alpha1-runstore").is_dir()
