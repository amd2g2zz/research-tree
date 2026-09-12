"""Run-phase discipline on the research-tree state (issue #492).

Covers the gated phase graph, the birth-phase rule, and the post-compile
realignment gate that binds a changed strategy authority fingerprint to a
fresh user realignment record.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pytest

from research_tree import RunLedger
from research_tree.domain import ArtifactRef, thaw_json
from research_tree.recursive_search import initialize_research_state
from research_tree.tree_state import (
    DEFAULT_TREE_PHASE,
    TREE_PHASE_TRANSITIONS,
    TREE_PHASES,
    CanonicalResearchTreeStateService,
    ResearchTreeStateError,
    tree_phase_of,
    validate_phase_transition,
    validate_tree_state_payload,
)

ROUND_ID = "round-phase"
TREE_ID = "research-tree"
FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64
CONFIRMATION_DIGEST = "c" * 64

# Every ordered phase pair except the gated edges and self-loops.
ILLEGAL_TRANSITIONS = [
    (previous, successor)
    for previous in sorted(TREE_PHASES)
    for successor in sorted(TREE_PHASES)
    if successor not in TREE_PHASE_TRANSITIONS[previous]
]


def _finding(finding_id: str) -> dict[str, object]:
    return {
        "id": finding_id,
        "decision_slot_id": "slot-architecture",
        "observations": [
            {
                "claim": "The architecture requires a replayable research state.",
                "anchor": {"kind": "source", "ref": "source:baseline"},
            }
        ],
        "option_effects": [{"option": "persistent-tree", "effect": "supports"}],
        "remaining_uncertainties": [],
        "research_continuations": [],
        "validation_result": None,
    }


def _slots() -> dict[str, dict[str, object]]:
    return {
        "slot-architecture": {
            "status": "open",
            "priority": "P0",
            "uncertainty": "high",
            "question": "How should recursive research state be maintained?",
            "validation": {"oracle": "restart and replay preserves the active frontier"},
        }
    }


def _fresh_state(baseline_findings: Sequence[object] = (), **overrides: object) -> dict[str, object]:
    state = initialize_research_state(
        round_id=ROUND_ID,
        tree_id=TREE_ID,
        decision_slots=_slots(),
        baseline_findings=baseline_findings,
    )
    state.update(overrides)
    return state


def _service_with_tree(tmp_path: Path, **overrides: object):
    ledger = RunLedger(tmp_path / "run-ledger")
    ledger.create_run(ROUND_ID)
    baseline = ledger.append_artifact(
        ROUND_ID,
        "finding-baseline",
        "finding-pack",
        _finding("finding-baseline"),
        expected_revision=ledger.get_revision(ROUND_ID),
    )
    service = CanonicalResearchTreeStateService(ledger)
    first = service.initialize(
        round_id=ROUND_ID,
        tree_id=TREE_ID,
        state=_fresh_state(baseline_findings=(baseline,), **overrides),
        baseline_findings=(baseline,),
        expected_revision=ledger.get_revision(ROUND_ID),
    )
    return ledger, service, first


def _next_state(previous_payload: dict[str, object], **overrides: object) -> dict[str, object]:
    state = thaw_json(previous_payload)
    state["transition_index"] = int(previous_payload["transition_index"]) + 1
    state.update(overrides)
    return state


def _realignment_record(fingerprint: str, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": 1,
        "confirmation_digest": CONFIRMATION_DIGEST,
        "authority_fingerprint": fingerprint,
        "reason": "user reconfirmed the revised strategy",
    }
    record.update(overrides)
    return record


def test_transition_table_keeps_the_gated_graph() -> None:
    assert TREE_PHASES == {"intake", "alignment", "compiled", "research", "validation", "delivery"}
    assert DEFAULT_TREE_PHASE == "compiled"
    assert TREE_PHASE_TRANSITIONS == {
        "intake": {"intake", "alignment"},
        "alignment": {"alignment", "compiled"},
        "compiled": {"compiled", "research", "alignment"},
        "research": {"research", "validation", "alignment"},
        "validation": {"validation", "delivery"},
        "delivery": {"delivery"},
    }


@pytest.mark.parametrize(("previous", "successor"), ILLEGAL_TRANSITIONS)
def test_every_illegal_phase_transition_is_rejected(previous: str, successor: str) -> None:
    with pytest.raises(ResearchTreeStateError, match="illegal tree phase transition"):
        validate_phase_transition(previous, successor)


@pytest.mark.parametrize(
    ("previous", "successor"),
    sorted(
        (previous, successor) for previous, successors in TREE_PHASE_TRANSITIONS.items() for successor in successors
    ),
)
def test_every_legal_phase_transition_is_accepted(previous: str, successor: str) -> None:
    validate_phase_transition(previous, successor)


def test_service_initialize_defaults_birth_phase_to_compiled(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path)
    latest = service.latest(round_id=ROUND_ID, tree_id=TREE_ID)
    assert latest == first
    assert latest.payload["phase"] == "compiled"


def test_initialize_rejects_non_compiled_birth_phase(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path / "run-ledger")
    ledger.create_run(ROUND_ID)
    baseline = ledger.append_artifact(
        ROUND_ID,
        "finding-baseline",
        "finding-pack",
        _finding("finding-baseline"),
        expected_revision=ledger.get_revision(ROUND_ID),
    )
    service = CanonicalResearchTreeStateService(ledger)
    with pytest.raises(ResearchTreeStateError, match="birth phase"):
        service.initialize(
            round_id=ROUND_ID,
            tree_id=TREE_ID,
            state=_fresh_state(phase="research"),
            baseline_findings=(baseline,),
            expected_revision=ledger.get_revision(ROUND_ID),
        )


def test_validate_rejects_unknown_phase(tmp_path: Path) -> None:
    _ledger, _service, first = _service_with_tree(tmp_path)
    with pytest.raises(ResearchTreeStateError, match="tree state phase is unsupported"):
        validate_tree_state_payload({**thaw_json(first.payload), "phase": "flying"})


def test_validate_and_phase_helper_accept_legacy_payload_without_phase(tmp_path: Path) -> None:
    _ledger, _service, first = _service_with_tree(tmp_path)
    legacy = thaw_json(first.payload)
    legacy.pop("phase")
    validate_tree_state_payload(legacy)
    assert tree_phase_of(legacy) == "compiled"


def test_service_transition_rejects_illegal_claim_from_stored_state(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path)
    with pytest.raises(ResearchTreeStateError, match="illegal tree phase transition"):
        service.transition(
            round_id=ROUND_ID,
            previous=first,
            state=_next_state(first.payload, phase="delivery"),
            consumed_findings=(),
            expected_revision=(first.revision + 1),
        )


def test_compiled_tree_walks_research_validation_delivery(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path)
    revision = first.revision + 1
    previous = first
    for phase in ("research", "validation", "delivery"):
        previous = service.transition(
            round_id=ROUND_ID,
            previous=previous,
            state=_next_state(previous.payload, phase=phase),
            consumed_findings=(),
            expected_revision=revision,
        )
        revision += 1
        assert previous.payload["phase"] == phase
    assert service.latest(round_id=ROUND_ID, tree_id=TREE_ID).payload["phase"] == "delivery"


def test_reopen_alignment_path_reenters_through_recompile(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path)
    revision = first.revision + 1
    research = service.transition(
        round_id=ROUND_ID,
        previous=first,
        state=_next_state(first.payload, phase="research"),
        consumed_findings=(),
        expected_revision=revision,
    )
    reopened = service.transition(
        round_id=ROUND_ID,
        previous=research,
        state=_next_state(research.payload, phase="alignment"),
        consumed_findings=(),
        expected_revision=revision + 1,
    )
    assert reopened.payload["phase"] == "alignment"
    recompiled = service.transition(
        round_id=ROUND_ID,
        previous=reopened,
        state=_next_state(reopened.payload, phase="compiled"),
        consumed_findings=(),
        expected_revision=revision + 2,
    )
    assert recompiled.payload["phase"] == "compiled"
    assert service.latest(round_id=ROUND_ID, tree_id=TREE_ID).payload["phase"] == "compiled"


def test_rogue_delivery_state_cannot_reenter_research(tmp_path: Path) -> None:
    ledger, service, first = _service_with_tree(tmp_path)
    rogue_payload = thaw_json(first.payload)
    rogue_payload["phase"] = "delivery"
    rogue_payload["transition_index"] = 1
    ledger.append_artifact(
        ROUND_ID,
        TREE_ID,
        "research-tree-state",
        rogue_payload,
        parent_refs=(ArtifactRef(first.round_id, first.id, first.revision),),
        expected_revision=first.revision + 1,
    )
    rogue = service.latest(round_id=ROUND_ID, tree_id=TREE_ID)
    with pytest.raises(ResearchTreeStateError, match="illegal tree phase transition"):
        service.transition(
            round_id=ROUND_ID,
            previous=rogue,
            state=_next_state(rogue.payload, phase="research"),
            consumed_findings=(),
            expected_revision=rogue.revision + 1,
        )


def test_fingerprint_change_without_realignment_is_rejected(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    with pytest.raises(ResearchTreeStateError, match="realignment"):
        service.transition(
            round_id=ROUND_ID,
            previous=first,
            state=_next_state(first.payload, phase="research", strategy_authority_fingerprint=FINGERPRINT_B),
            consumed_findings=(),
            expected_revision=first.revision + 1,
        )


def test_fingerprint_change_outside_recompile_edge_is_rejected_even_with_record(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    revision = first.revision + 1
    research = service.transition(
        round_id=ROUND_ID,
        previous=first,
        state=_next_state(first.payload, phase="research"),
        consumed_findings=(),
        expected_revision=revision,
    )
    with pytest.raises(ResearchTreeStateError, match="realignment"):
        service.transition(
            round_id=ROUND_ID,
            previous=research,
            state=_next_state(
                research.payload,
                phase="research",
                strategy_authority_fingerprint=FINGERPRINT_B,
                realignment=_realignment_record(FINGERPRINT_B),
            ),
            consumed_findings=(),
            expected_revision=revision + 1,
        )


def test_realignment_recompile_with_record_is_accepted(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    revision = first.revision + 1
    reopened = service.transition(
        round_id=ROUND_ID,
        previous=first,
        state=_next_state(first.payload, phase="alignment"),
        consumed_findings=(),
        expected_revision=revision,
    )
    recompiled = service.transition(
        round_id=ROUND_ID,
        previous=reopened,
        state=_next_state(
            reopened.payload,
            phase="compiled",
            strategy_authority_fingerprint=FINGERPRINT_B,
            realignment=_realignment_record(FINGERPRINT_B),
        ),
        consumed_findings=(),
        expected_revision=revision + 1,
    )
    assert recompiled.payload["strategy_authority_fingerprint"] == FINGERPRINT_B
    assert service.latest(round_id=ROUND_ID, tree_id=TREE_ID) == recompiled


def test_reopened_alignment_keeps_the_recorded_fingerprint(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    reopened = service.transition(
        round_id=ROUND_ID,
        previous=first,
        state=_next_state(first.payload, phase="alignment"),
        consumed_findings=(),
        expected_revision=first.revision + 1,
    )
    assert reopened.payload["strategy_authority_fingerprint"] == FINGERPRINT_A


def test_fingerprint_drop_requires_realignment_edge(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    state = _next_state(first.payload, phase="research")
    state.pop("strategy_authority_fingerprint")
    with pytest.raises(ResearchTreeStateError, match="realignment"):
        service.transition(
            round_id=ROUND_ID,
            previous=first,
            state=state,
            consumed_findings=(),
            expected_revision=first.revision + 1,
        )


def test_fingerprint_adoption_without_prior_fingerprint_is_allowed(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path)
    adopted = service.transition(
        round_id=ROUND_ID,
        previous=first,
        state=_next_state(first.payload, phase="research", strategy_authority_fingerprint=FINGERPRINT_A),
        consumed_findings=(),
        expected_revision=first.revision + 1,
    )
    assert adopted.payload["strategy_authority_fingerprint"] == FINGERPRINT_A


def test_realignment_record_must_bind_the_payload_fingerprint(tmp_path: Path) -> None:
    _ledger, _service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    payload = thaw_json(first.payload)
    payload["realignment"] = _realignment_record(FINGERPRINT_B)
    with pytest.raises(ResearchTreeStateError, match="realignment record"):
        validate_tree_state_payload(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirmation_digest": "not-hex"},
        {"authority_fingerprint": "zz" * 32},
        {"schema": 2},
        {"reason": ""},
        {"extra_key": "no"},
    ],
)
def test_malformed_realignment_record_is_rejected(overrides: dict[str, object], tmp_path: Path) -> None:
    _ledger, _service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    payload = thaw_json(first.payload)
    payload["realignment"] = _realignment_record(FINGERPRINT_A, **overrides)
    with pytest.raises(ResearchTreeStateError, match="realignment"):
        validate_tree_state_payload(payload)


@pytest.mark.parametrize("fingerprint", ["nothex", FINGERPRINT_A.upper(), 12345])
def test_malformed_strategy_fingerprint_is_rejected(fingerprint: object, tmp_path: Path) -> None:
    _ledger, _service, first = _service_with_tree(tmp_path)
    payload = thaw_json(first.payload)
    payload["strategy_authority_fingerprint"] = fingerprint
    with pytest.raises(ResearchTreeStateError, match="strategy_authority_fingerprint"):
        validate_tree_state_payload(payload)


def test_transition_rejects_mutation_outside_legal_edges_at_json_boundary(tmp_path: Path) -> None:
    """A payload claiming a legal phase but a stale transition index still fails."""

    _ledger, service, first = _service_with_tree(tmp_path)
    state = _next_state(first.payload, phase="delivery")
    state["transition_index"] = 5
    with pytest.raises(ResearchTreeStateError, match="transition_index"):
        service.transition(
            round_id=ROUND_ID,
            previous=first,
            state=state,
            consumed_findings=(),
            expected_revision=first.revision + 1,
        )


def test_realignment_payload_survives_a_json_round_trip(tmp_path: Path) -> None:
    _ledger, service, first = _service_with_tree(tmp_path, strategy_authority_fingerprint=FINGERPRINT_A)
    reopened = service.transition(
        round_id=ROUND_ID,
        previous=first,
        state=_next_state(first.payload, phase="alignment"),
        consumed_findings=(),
        expected_revision=first.revision + 1,
    )
    serialized = json.loads(json.dumps(thaw_json(_next_state(reopened.payload))))
    recompiled = service.transition(
        round_id=ROUND_ID,
        previous=reopened,
        state={
            **serialized,
            "phase": "compiled",
            "strategy_authority_fingerprint": FINGERPRINT_B,
            "realignment": _realignment_record(FINGERPRINT_B),
        },
        consumed_findings=(),
        expected_revision=reopened.revision + 1,
    )
    assert recompiled.payload["realignment"]["confirmation_digest"] == CONFIRMATION_DIGEST
