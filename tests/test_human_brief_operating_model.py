"""Issue #452: the Human Brief exposes the operating model (#292 gate 8 pre-work).

Every operating-model field is sourced from real run artifacts — the confirmed
StrategyProjection, per-oracle ``goal_satisfaction`` registrations, and the
coordinator's ``why_not_complete`` resolve entries — never from hand-filled
placeholder values. SLA, concurrency limits, and adoption metrics are
baseline-run dimensions: fields are present, values are labeled as baselines,
not commitments.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from test_deliveries import compile_deliveries, context
from test_goal_wiring import confirm_projection, projection

from research_tree import ArtifactRef
from research_tree.completion_inputs import CompletionInputRegistrar
from research_tree.coordinator import GOAL_CONTRIBUTION_ASSESSMENT_KIND
from research_tree.delivery import validate_human_brief_payload
from research_tree.domain import canonical_json_bytes, thaw_json
from research_tree.strategy_projection import authority_fingerprint

ROOT = Path(__file__).resolve().parents[1]
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
ORACLE_ALPHA = {"id": "oracle-alpha", "evidence_standard_ids": ("standard-1",)}
ORACLE_BETA = {"id": "oracle-beta", "evidence_standard_ids": ("standard-2",)}


def _confirmed_goal_projection(ledger, run_id: str, target):
    """Attach a confirmed StrategyProjection to the delivery fixture run."""

    handoff = ledger.append_artifact(
        run_id,
        "handoff-1",
        "alignment-handoff",
        {"confirmed": True},
        expected_revision=ledger.get_revision(run_id),
    )
    frame = ledger.append_artifact(
        run_id,
        "strategy-frame",
        "decision-frame",
        {"status": "ready_for_strategy"},
        expected_revision=ledger.get_revision(run_id),
    )
    goal_projection = projection(
        run_id,
        frame_ref=ArtifactRef(run_id, frame.id, frame.revision),
        handoff_ref=ArtifactRef(run_id, handoff.id, handoff.revision),
        target_ref=ArtifactRef(run_id, target.id, target.revision),
        success_oracles=(ORACLE_ALPHA, ORACLE_BETA),
    )
    confirm_projection(ledger, run_id, goal_projection)
    return goal_projection


def _register_verdict(ledger, run_id: str, oracle_id: str, verdict: str, pack_id: str, *, waiver_reason=None):
    pack = ledger.append_artifact(
        run_id,
        pack_id,
        "finding-pack",
        {"id": pack_id, "round_id": run_id},
        expected_revision=ledger.get_revision(run_id),
    )
    CompletionInputRegistrar(ledger).write_goal_satisfaction(
        round_id=run_id,
        registration_id=f"goal-{oracle_id}",
        oracle_id=oracle_id,
        verdict=verdict,
        evidence_refs=(ArtifactRef(run_id, pack.id, pack.revision),),
        waiver_reason=waiver_reason,
        expected_revision=ledger.get_revision(run_id),
    )


def _append_contribution(ledger, run_id: str, contribution_id: str, slot_id: str, pack_id: str, verdict: str):
    return ledger.append_artifact(
        run_id,
        contribution_id,
        GOAL_CONTRIBUTION_ASSESSMENT_KIND,
        {
            "schema": 1,
            "id": contribution_id,
            "round_id": run_id,
            "finding_pack_id": pack_id,
            "finding_pack_revision": 1,
            "slot_id": slot_id,
            "verdict": verdict,
            "reason": f"{verdict} on {slot_id}",
        },
        expected_revision=ledger.get_revision(run_id),
    )


def _append_run_state(ledger, run_id: str, state: str = "delivery_pending"):
    body = {
        "state": state,
        "lifecycle_revision": 1,
        "unmet_obligations": [],
        "legal_next_actions": [],
    }
    body["state_digest"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    target = next(item for item in ledger.load_run(run_id).artifacts if item.kind == "blueprint-target")
    return ledger.append_artifact(
        run_id,
        "run-state",
        "research-run-state",
        body,
        parent_refs=(ArtifactRef(run_id, target.id, target.revision),),
        expected_revision=ledger.get_revision(run_id),
    )


def _operating_model(human_brief) -> dict:
    return thaw_json(human_brief.payload["document"]["operating_model"])


# ---------------------------------------------------------------------------
# Data plane: real artifacts, fail-closed defaults
# ---------------------------------------------------------------------------


def test_operating_model_present_with_fail_closed_defaults(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)

    human = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).human_brief
    model = _operating_model(human)

    assert set(model) == {
        "schema",
        "roles",
        "outcome_layers",
        "blockers",
        "fallback_plan",
        "baseline_dimensions",
    }
    assert model["schema"] == 1
    assert [role["role"] for role in model["roles"]] == [
        "research_owner",
        "platform_integrator",
        "governance_auditor",
    ]
    for role in model["roles"]:
        assert set(role) == {"role", "responsibility", "handoff_surface"}
        assert role["responsibility"] and role["handoff_surface"]

    layers = model["outcome_layers"]
    assert set(layers) == {"confirmed_projection", "oracle_verdicts", "slot_contributions"}
    assert layers["confirmed_projection"] is None
    assert layers["oracle_verdicts"] == []
    assert layers["slot_contributions"] == []

    assert model["blockers"] == [
        {
            "obligation": "coordinator_state",
            "resolution_action": (
                "resolve:coordinator_state — the canonical run state is unavailable "
                "(run is not initialized); re-enter alignment to initialize the run"
            ),
            "owner_role": "research_owner",
        }
    ]

    assert model["fallback_plan"]
    for entry in model["fallback_plan"]:
        assert set(entry) == {"capability", "degraded_path"}
        assert entry["capability"] and entry["degraded_path"]

    assert set(model["baseline_dimensions"]) == {"sla", "concurrency_limits", "adoption_metrics"}
    for field in model["baseline_dimensions"].values():
        assert field["basis"] == "baseline_run"
        assert field["dimension"]
        assert field["commitments"] is None


def test_operating_model_sourced_from_real_run_artifacts(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    run_id = round_record.id
    goal_projection = _confirmed_goal_projection(ledger, run_id, target)
    _register_verdict(ledger, run_id, "oracle-alpha", "satisfied", "pack-alpha")
    _append_contribution(ledger, run_id, "contribution-1", "slot-isolation", "pack-alpha", "serves")
    _append_run_state(ledger, run_id)

    human = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).human_brief
    model = _operating_model(human)

    layers = model["outcome_layers"]
    confirmed = layers["confirmed_projection"]
    assert confirmed["projection_id"] == "projection-1"
    assert confirmed["projection_revision"] == 1
    assert confirmed["display_digest"] == goal_projection.display_digest
    assert _HEX64.fullmatch(confirmed["authority_fingerprint"])
    assert confirmed["authority_fingerprint"] == authority_fingerprint(goal_projection)

    assert layers["oracle_verdicts"] == [
        {"oracle_id": "oracle-alpha", "verdict": "satisfied", "waiver_reason": None},
    ]

    assert layers["slot_contributions"] == [
        {
            "slot_id": "slot-isolation",
            "finding_pack_id": "pack-alpha",
            "verdict": "serves",
            "reason": "serves on slot-isolation",
        }
    ]

    actions = {entry["resolution_action"] for entry in model["blockers"]}
    owners = {entry["resolution_action"]: entry["owner_role"] for entry in model["blockers"]}
    assert "resolve:goal_satisfaction:oracle-beta" in actions
    assert owners["resolve:goal_satisfaction:oracle-beta"] == "research_owner"
    assert "resolve:acceptance_ref" in actions
    assert owners["resolve:acceptance_ref"] == "human_requester"
    assert all(entry["obligation"] != "coordinator_state" for entry in model["blockers"])


def test_operating_model_verdicts_reflect_current_registrations(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    run_id = round_record.id
    _confirmed_goal_projection(ledger, run_id, target)
    _register_verdict(ledger, run_id, "oracle-alpha", "satisfied", "pack-alpha")
    _register_verdict(
        ledger,
        run_id,
        "oracle-beta",
        "waived",
        "pack-beta",
        waiver_reason="oracle no longer reachable in this round",
    )
    _append_run_state(ledger, run_id)

    human = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).human_brief
    verdicts = _operating_model(human)["outcome_layers"]["oracle_verdicts"]

    assert verdicts == [
        {"oracle_id": "oracle-alpha", "verdict": "satisfied", "waiver_reason": None},
        {"oracle_id": "oracle-beta", "verdict": "waived", "waiver_reason": "oracle no longer reachable in this round"},
    ]


# ---------------------------------------------------------------------------
# Payload validation: whitelist + named errors
# ---------------------------------------------------------------------------


def _valid_payload(tmp_path: Path):
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    deliveries = compile_deliveries(modules, ledger, round_record, brief, target, [decision])
    return thaw_json(deliveries.human_brief.payload)


def test_validator_accepts_the_compiled_payload(tmp_path: Path) -> None:
    assert validate_human_brief_payload(_valid_payload(tmp_path)) is None


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["document"].pop("operating_model"),
            "human brief document has unexpected keys; missing=['operating_model']",
        ),
        (
            lambda payload: payload["document"]["operating_model"].update(extra="x"),
            "human brief operating model has unexpected keys",
        ),
        (
            lambda payload: payload["document"]["operating_model"].update(schema=2),
            "human brief operating model schema must be 1",
        ),
        (
            lambda payload: payload["document"]["operating_model"].update(
                roles=payload["document"]["operating_model"]["roles"][:2]
            ),
            "human brief operating model roles must name exactly three roles",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["roles"][0].pop("handoff_surface"),
            "human brief operating model roles[0] has unexpected keys",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["roles"][0].update(role="worker"),
            "human brief operating model roles[0].role must be one of",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["outcome_layers"].update(
                oracle_verdicts=({"oracle_id": "o", "verdict": "pending", "waiver_reason": None},)
            ),
            "human brief operating model outcome_layers oracle_verdicts[0].verdict must be one of",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["outcome_layers"].update(
                confirmed_projection={"projection_id": "p"}
            ),
            "human brief operating model outcome_layers confirmed_projection has unexpected keys",
        ),
        (
            lambda payload: payload["document"]["operating_model"].update(blockers=()),
            "human brief operating model blockers must not be empty",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["blockers"][0].pop("owner_role"),
            "human brief operating model blockers[0] has unexpected keys",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["blockers"][0].update(owner_role="team"),
            "human brief operating model blockers[0].owner_role must be one of",
        ),
        (
            lambda payload: payload["document"]["operating_model"].update(fallback_plan=()),
            "human brief operating model fallback_plan must not be empty",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["baseline_dimensions"].update(
                sla={"basis": "committed", "dimension": "x", "commitments": None}
            ),
            "human brief operating model baseline_dimensions sla basis must be baseline_run",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["baseline_dimensions"]["sla"].update(
                commitments={"alignment": "2 days"}
            ),
            "human brief operating model baseline_dimensions sla commitments must be null",
        ),
        (
            lambda payload: payload["document"]["operating_model"]["baseline_dimensions"].pop("adoption_metrics"),
            "human brief operating model baseline_dimensions has unexpected keys",
        ),
    ],
)
def test_validator_rejects_schema_drift_with_named_errors(tmp_path: Path, mutate, message: str) -> None:
    payload = _valid_payload(tmp_path)
    mutate(payload)

    with pytest.raises(Exception, match=re.escape(message)):
        validate_human_brief_payload(payload)


# ---------------------------------------------------------------------------
# Rendered markdown: fields present, never placeholders
# ---------------------------------------------------------------------------


def test_rendered_markdown_exposes_all_seven_operating_model_fields(tmp_path: Path) -> None:
    modules, ledger, round_record, _model, brief, target, _finding, decision = context(tmp_path)
    run_id = round_record.id
    goal_projection = _confirmed_goal_projection(ledger, run_id, target)
    _register_verdict(ledger, run_id, "oracle-alpha", "satisfied", "pack-alpha")
    _append_run_state(ledger, run_id)

    markdown = compile_deliveries(modules, ledger, round_record, brief, target, [decision]).human_brief.payload[
        "markdown"
    ]

    assert "## Operating Model" in markdown
    for heading in (
        "### Roles",
        "### SLA (baseline run)",
        "### Concurrency limits (baseline run)",
        "### Blockers",
        "### Outcome layers",
        "### Adoption metrics (baseline run)",
        "### Fallback plan",
    ):
        assert heading in markdown
    assert goal_projection.display_digest in markdown
    assert "resolve:goal_satisfaction:oracle-beta" in markdown
    assert "research_owner" in markdown
    assert "human_requester" in markdown
    assert "baseline run" in markdown
    assert "{{" not in markdown
    assert "}}" not in markdown


# ---------------------------------------------------------------------------
# Template: seven-field structure with real data-source annotations
# ---------------------------------------------------------------------------


def test_template_structures_the_seven_operating_model_fields() -> None:
    template = (ROOT / "assets" / "human-brief-template.md").read_text(encoding="utf-8")

    for heading in (
        "## Roles",
        "## SLA",
        "## Concurrency limits",
        "## Blockers",
        "## Outcome layers",
        "## Adoption metrics",
        "## Fallback plan",
    ):
        assert heading in template
    assert "baseline run" in template
    assert "goal_satisfaction" in template
    assert "why_not_complete" in template
    assert "confirmed projection" in template
    assert "when the checkout runtime is available" in template
    assert "Alignment Trace" in template
    assert "research owner" in template
    assert "platform integrator" in template
    assert "governance auditor" in template
