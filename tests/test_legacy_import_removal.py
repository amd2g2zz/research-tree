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
    registry_root = (
        Path(__file__).resolve().parents[1] / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"
    )
    execution = json.loads((registry_root / "task-execution-v1.json").read_text(encoding="utf-8"))
    verification = json.loads((registry_root / "task-verification-v1.json").read_text(encoding="utf-8"))
    issue_map = json.loads((registry_root / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    matrix = json.loads((registry_root / "delivery-matrix-v1.json").read_text(encoding="utf-8"))

    assert 34 not in {item["group"] for item in execution["groups"]}
    assert 34 not in {item["group"] for item in verification["groups"]}
    assert {item["group"] for item in execution["groups"]} >= {55}
    assert next(item for item in verification["groups"] if item["group"] == 55)["state"] == "verified"
    assert all("legacy-runstore-import" not in item["capabilities"] for item in issue_map["issues"])
    assert all(item["capability"] != "legacy-runstore-import" for item in matrix["capability_rows"])
