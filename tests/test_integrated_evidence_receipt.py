"""Acceptance checks for the source-bound #112 integration receipt."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from research_tree.openspec_governance import (
    default_registry_paths,
    load_governance_inputs,
    validate_governance,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"
RECEIPT = (
    ROOT
    / "openspec"
    / "changes"
    / "reconcile-foundation-verification-receipts"
    / "evidence"
    / "integrated-strict-slices.json"
)


def test_integrated_receipt_records_merged_slices_and_boundary() -> None:
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["kind"] == "integrated_verification_receipt"
    assert re.fullmatch(r"[0-9a-f]{40}", payload["source_revision"])

    merged = {(item["issue"], item["pull_request"]): item["merge_revision"] for item in payload["merged_slices"]}
    assert merged == {
        (111, 115): "6bb8cfa",
        (108, 116): "5539e92",
        (110, 122): "540014f",
        (109, 123): "63164fb",
    }

    boundary = payload["boundary"]
    assert boundary == {
        "current_issue": 112,
        "legacy_worker_validation_guard_issue": 109,
        "oracle_slot_closure_issue": 56,
        "parent_tracker_issue": 106,
    }

    for command in payload["commands"]:
        assert command["exit_code"] == 0
        raw_output = ROOT / command["raw_output_ref"]
        raw_bytes = raw_output.read_bytes()
        assert command["output_digest"] == hashlib.sha256(raw_bytes).hexdigest()


def test_group_35_owns_integrated_receipt_and_future_gaps_remain_unverified() -> None:
    inputs = load_governance_inputs(*default_registry_paths(ROOT))
    report = validate_governance(inputs)

    assert report.valid is True
    assert report.verified_groups == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 20, 23, 28, 31, 32, 33, 34, 35)
    assert report.unverified_groups == tuple(
        group for group in range(6, 33) if group not in {6, 7, 8, 9, 10, 11, 14, 16, 20, 23, 28, 31, 32}
    )

    issue_map = json.loads((REGISTRY_ROOT / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    row = next(item for item in issue_map["issues"] if item["issue"] == 112)
    assert row["primary_group"] == 35
    assert "integrated-evidence-reconciliation" in row["capabilities"]

    gaps = json.loads(
        (
            ROOT
            / "openspec"
            / "changes"
            / "reconcile-foundation-verification-receipts"
            / "evidence"
            / "future-evidence-gaps.json"
        ).read_text(encoding="utf-8")
    )
    assert gaps["schema_version"] == 1
    assert {item["group"] for item in gaps["gaps"]} == set(range(6, 33))
    assert all(item["state"] == "planned" for item in gaps["gaps"])
