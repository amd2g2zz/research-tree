"""senior-user-ux-v2 projection success oracles (#292 gates -> falsifiable oracles).

The oracle set is the mechanical half of the #292 closure path: every closure
gate and follow-up metric must be carried by at least one projection success
oracle whose evidence standards name where the run must produce matching
tokens, and the assembled set must pass ``validate_falsifiability`` on a real
``StrategyProjection``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation" / "harness"))

from v2_oracles import (  # noqa: E402
    BASELINE_RUN_NAME,
    CLOSURE_GATES,
    DECISION_TARGETS,
    EVIDENCE_STANDARDS,
    METRIC_COVERAGE,
    RUN_NAME,
    SUCCESS_ORACLES,
    build_decision_targets,
    build_success_oracles,
)

from research_tree.domain import ArtifactRef  # noqa: E402
from research_tree.strategy_projection import (  # noqa: E402
    StrategyProjection,
    StrategyProjectionError,
    validate_falsifiability,
)

GATE_RANGE = frozenset(CLOSURE_GATES)
# 1 role-score rule + 12 tracked metrics + 1 noise criterion from #292.
EXPECTED_METRIC_COUNT = 14


def _fixture_projection(success_oracles, decision_targets) -> StrategyProjection:
    run_id = "run-v2-oracles-fixture"
    ref = ArtifactRef(run_id, "blueprint-target", 1)
    return StrategyProjection.create(
        projection_id="strategy-projection",
        run_id=run_id,
        decision_frame_ref=ArtifactRef(run_id, "strategy-frame", 1),
        alignment_handoff_ref=ArtifactRef(run_id, "alignment-handoff", 1),
        target_ref=ref,
        current_understanding="Close the #292 adoption gates with a fresh dual-track evaluation.",
        assumptions=("baseline roles re-run the 8/20 protocol",),
        decision_targets=decision_targets,
        tracks=({"id": "track-a"}, {"id": "track-b"}),
        method_hypotheses=({"method": "governed-runtime"},),
        depth="deep",
        evidence_expectations=("canonical receipts",),
        autonomy_envelope={"allowed": ["evaluation"], "authority": "research_owner"},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=success_oracles,
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="every served oracle carries gate-bound evidence or the run stays open",
        preference_influences=(),
        revision=1,
        status="displayed",
    )


def test_run_and_baseline_names_match_evidence_convention():
    assert RUN_NAME == "senior-user-ux-v2"
    assert BASELINE_RUN_NAME == "senior-user-ux-20260820"


def test_every_oracle_carries_unique_id_statement_and_known_standards():
    ids = [oracle["id"] for oracle in SUCCESS_ORACLES]
    assert len(ids) == len(set(ids))
    for oracle in SUCCESS_ORACLES:
        assert oracle["statement"].strip()
        assert oracle["gate_ids"], oracle["id"]
        assert set(oracle["gate_ids"]) <= GATE_RANGE
        standards = oracle["evidence_standard_ids"]
        assert standards, oracle["id"]
        assert set(standards) <= set(EVIDENCE_STANDARDS), oracle["id"]


def test_every_standard_declares_statement_and_token_basis():
    for standard_id, standard in EVIDENCE_STANDARDS.items():
        assert standard_id == standard_id.strip() and standard_id
        assert standard["statement"].strip(), standard_id
        assert standard["token_basis"].strip(), standard_id


def test_every_closure_gate_is_covered_by_at_least_one_oracle():
    covered = {gate for oracle in SUCCESS_ORACLES for gate in oracle["gate_ids"]}
    assert covered == GATE_RANGE


def test_every_followup_metric_maps_to_at_least_one_known_oracle():
    known = {oracle["id"] for oracle in SUCCESS_ORACLES}
    assert len(METRIC_COVERAGE) == EXPECTED_METRIC_COUNT
    for metric, oracle_ids in METRIC_COVERAGE:
        assert oracle_ids, metric
        assert set(oracle_ids) <= known, metric
    assert len(METRIC_COVERAGE) == len({metric for metric, _ in METRIC_COVERAGE})


def test_decision_targets_reference_known_oracles_and_own_all_of_them():
    known = {oracle["id"] for oracle in SUCCESS_ORACLES}
    referenced = set()
    for target in DECISION_TARGETS:
        assert target["statement"].strip(), target["id"]
        assert target["oracle_ids"], target["id"]
        assert set(target["oracle_ids"]) <= known, target["id"]
        referenced |= set(target["oracle_ids"])
    assert referenced == known, "every oracle must be owned by a decision target"


def test_real_oracle_set_passes_validate_falsifiability():
    projection = _fixture_projection(build_success_oracles(), build_decision_targets())
    validate_falsifiability(projection)


def test_oracle_without_evidence_standard_is_rejected():
    oracles = [dict(oracle) for oracle in build_success_oracles()]
    oracles[0]["evidence_standard_ids"] = ()
    projection = _fixture_projection(tuple(oracles), build_decision_targets())
    with pytest.raises(StrategyProjectionError):
        validate_falsifiability(projection)


def test_dangling_target_oracle_reference_is_rejected():
    targets = [dict(target) for target in build_decision_targets()]
    targets[0]["oracle_ids"] = (*targets[0]["oracle_ids"], "oracle-does-not-exist")
    projection = _fixture_projection(build_success_oracles(), tuple(targets))
    with pytest.raises(StrategyProjectionError):
        validate_falsifiability(projection)


def test_noise_oracle_binds_the_baseline_comparison_criterion():
    noise = next(oracle for oracle in SUCCESS_ORACLES if oracle["id"] == "oracle-noise-reduction")
    assert "70%" in noise["statement"]
    assert BASELINE_RUN_NAME in noise["statement"]
