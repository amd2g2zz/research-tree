from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research_tree import synthesize_insights, validate_insight_digest


def pack(finding_id: str, slot_id: str = "slot-architecture") -> dict:
    return {
        "id": finding_id,
        "decision_slot_id": slot_id,
        "observations": [{"claim": "A claim", "anchor": {"kind": "source", "ref": f"source:{finding_id}"}}],
    }


def test_digest_rejects_wrong_slot_and_duplicate_finding_lineage() -> None:
    with pytest.raises(ValueError, match="active Decision Slot"):
        synthesize_insights([pack("finding-duplicate", "slot-other")], active_slot_ids=("slot-architecture",))
    with pytest.raises(ValueError, match="duplicate Finding Pack"):
        synthesize_insights(
            [pack("finding-duplicate"), pack("finding-duplicate")], active_slot_ids=("slot-architecture",)
        )


def test_duplicate_digest_batch_records_zero_change_and_no_growth_trigger() -> None:
    value = pack("finding-stable")
    value["observations"].append({"claim": "A claim", "anchor": {"kind": "repository", "ref": "src/runtime.py:1"}})
    first = synthesize_insights([value], active_slot_ids=("slot-architecture",))
    second = synthesize_insights([value], active_slot_ids=("slot-architecture",), previous_digest=first)
    assert second["realized_delta"]["no_change"] is True
    assert second["realized_delta"]["penalty"] == "no_progress"
    assert second["recommended_actions"]


def test_current_digest_round_trips_and_prior_minimal_digest_is_rejected() -> None:
    current = synthesize_insights([pack("finding-current")], active_slot_ids=("slot-architecture",))

    validate_insight_digest(current)
    continued = synthesize_insights(
        [pack("finding-current")],
        active_slot_ids=("slot-architecture",),
        previous_digest=current,
    )
    assert continued["previous_digest_ref"] == current["digest_id"]

    prior_minimal = {key: current[key] for key in ("insights", "next_actions", "closure", "finding_pack_count")}
    with pytest.raises(ValueError, match="schema_version"):
        validate_insight_digest(prior_minimal)
    with pytest.raises(ValueError, match="schema_version"):
        synthesize_insights(
            [pack("finding-next")],
            active_slot_ids=("slot-architecture",),
            previous_digest=prior_minimal,
        )

    prior_alias = dict(current)
    prior_alias["statements"] = prior_alias.pop("classified_statements")
    with pytest.raises(ValueError, match="classified_statements"):
        validate_insight_digest(prior_alias)


def test_current_digest_rejects_every_missing_required_field() -> None:
    current = synthesize_insights([pack("finding-complete")], active_slot_ids=("slot-architecture",))

    for field in current:
        incomplete = dict(current)
        incomplete.pop(field)
        with pytest.raises(ValueError, match=field):
            validate_insight_digest(incomplete)


def test_active_contracts_publish_only_the_current_insight_digest_payload() -> None:
    root = Path(__file__).parents[1]
    current = synthesize_insights([pack("finding-schema")], active_slot_ids=("slot-architecture",))
    schema = json.loads(
        (root / "openspec/changes/unify-research-runtime-alpha2/schemas/insight-digest-v1.json").read_text(
            encoding="utf-8"
        )
    )
    examples = json.loads(
        (root / "openspec/changes/unify-research-runtime-alpha2/schemas/examples/index-v1.json").read_text(
            encoding="utf-8"
        )
    )
    example = next(item for item in examples["entries"] if item["schema"] == "insight-digest-v1.json")

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(current)
    assert set(schema["properties"]) == set(current)
    assert set(example["valid"]) == set(current)
    assert "statements" not in schema["properties"]
    assert "classified_statements" in schema["properties"]

    umbrella = root / "openspec/changes/unify-research-runtime-alpha2"
    registry = umbrella / "registries"
    execution = json.loads((registry / "task-execution-v1.json").read_text(encoding="utf-8"))
    verification = json.loads((registry / "task-verification-v1.json").read_text(encoding="utf-8"))
    issue_map = json.loads((registry / "issue-execution-map-v1.json").read_text(encoding="utf-8"))
    matrix = json.loads((registry / "delivery-matrix-v1.json").read_text(encoding="utf-8"))

    assert next(item for item in execution["groups"] if item["group"] == 60)["outputs"] == [
        "current-insight-payload-reader"
    ]
    verification_record = next(item for item in verification["groups"] if item["group"] == 60)
    assert verification_record["state"] == "verified"
    assert verification_record["evidence_refs"] == [
        "openspec/changes/remove-legacy-insight-payload-reader/evidence/group-60-output.txt",
        "openspec/changes/remove-legacy-insight-payload-reader/evidence/group-60-receipt.json",
    ]
    receipt = verification_record["command_receipt"]
    assert receipt["exit_code"] == 0
    assert receipt["source_revision"] == "fdb74043df4fa0f0bd31c8023d83f991550bb775"
    assert receipt["raw_output_ref"] == verification_record["evidence_refs"][0]
    assert receipt == json.loads((root / verification_record["evidence_refs"][1]).read_text(encoding="utf-8"))
    assert hashlib.sha256((root / receipt["raw_output_ref"]).read_bytes()).hexdigest() == receipt["output_digest"]
    assert next(item for item in issue_map["issues"] if item["issue"] == 174) == {
        "issue": 174,
        "primary_group": 60,
        "supporting_groups": [],
        "capabilities": ["current-insight-payload-reader"],
        "openspec_change": "remove-legacy-insight-payload-reader",
    }
    assert any(
        item["capability"] == "current-insight-payload-reader" and item["task_groups"] == [60]
        for item in matrix["capability_rows"]
    )

    parser_source = (root / "src/research_tree/insights.py").read_text(encoding="utf-8")
    active_contract = (umbrella / "specs/insight-synthesis/spec.md").read_text(encoding="utf-8")
    assert 'if "schema_version" not in value:' not in parser_source
    assert "_LEGACY_REQUIRED" not in parser_source
    assert "SHALL NOT provide a compatibility reader" in active_contract
