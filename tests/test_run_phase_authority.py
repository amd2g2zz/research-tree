"""Run phase authority (issue #530).

The phase clock gets its hands: owned writers at each owning transition, a
run-level authoritative phase store (engine-written JSON with digest), hook
resolution that reads the authority before env/manifest guesses, phase-aware
alignment plan/record refusal under ``research``, and cache-friendly grounding
(one append-only event statement per transition turn plus a single-line
fixed-slot tail snapshot — never a per-turn state block in the prompt body).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_alignment_controller import complete_graph, controller, write_json
from test_research_run_coordinator import (
    _confirm_strategy,
    _initialize,
    _register_canonical_completion_inputs,
)

from research_tree.alignment_graph import AlignmentGraphError
from research_tree.alignment_handoff import initialize_research_from_alignment
from research_tree.coordinator import RESEARCH_RUN_STATE_KIND, ResearchRunCoordinator
from research_tree.lifecycle_hook import (
    build_phase_snapshot,
    observe,
)
from research_tree.run_ledger import RunLedger
from research_tree.tree_state import (
    DEFAULT_TREE_PHASE,
    CanonicalResearchTreeStateService,
    ResearchTreeStateError,
    RunPhaseStore,
    render_phase_event,
    run_phase_dir,
)

RUN_ID = "run-57"
TREE_ID = f"tree-{RUN_ID}"


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


def _birth_tree(ledger: RunLedger, *, round_id: str = RUN_ID, tree_id: str = TREE_ID):
    """Birth a tree through the canonical service (born ``compiled``)."""

    from research_tree.recursive_search import initialize_research_state

    baseline = ledger.append_artifact(
        round_id,
        "finding-baseline",
        "finding-pack",
        _finding("finding-baseline"),
        expected_revision=ledger.get_revision(round_id),
    )
    service = CanonicalResearchTreeStateService(ledger)
    state = initialize_research_state(
        round_id=round_id,
        tree_id=tree_id,
        decision_slots=_slots(),
        baseline_findings=(baseline,),
    )
    return service.initialize(
        round_id=round_id,
        tree_id=tree_id,
        state=state,
        baseline_findings=(baseline,),
        expected_revision=ledger.get_revision(round_id),
    )


def _store(tmp_path: Path, run_id: str = RUN_ID) -> RunPhaseStore:
    return RunPhaseStore(run_phase_dir(tmp_path, run_id))


def _promote_to_autonomous_research(tmp_path: Path) -> tuple[RunLedger, ResearchRunCoordinator]:
    """A run whose workflow reached autonomous_research and whose tree is born."""

    ledger, coordinator, _handoff, _target, _state = _initialize(tmp_path)
    _birth_tree(ledger)
    _confirm_strategy(ledger, coordinator)
    return ledger, coordinator


def _promote_to_delivery_ready(tmp_path: Path) -> tuple[RunLedger, ResearchRunCoordinator]:
    """A run at autonomous_research with completion inputs registered."""

    ledger, coordinator, _handoff, target, _state = _initialize(tmp_path)
    _birth_tree(ledger)
    _confirm_strategy(ledger, coordinator)
    _register_canonical_completion_inputs(ledger, RUN_ID, target, review=False)
    return ledger, coordinator


def _prompt_payload(tmp_path: Path, prompt: str, run_id: str = RUN_ID) -> dict[str, object]:
    return {"cwd": str(tmp_path), "run_id": run_id, "prompt": prompt}


def _submit(tmp_path: Path, prompt: str, run_id: str = RUN_ID) -> dict:
    return observe(
        _prompt_payload(tmp_path, prompt, run_id),
        host="claude",
        event="UserPromptSubmit",
        project_root=tmp_path,
        process_cwd=tmp_path,
    )


def test_full_run_phase_sequence_persisted_and_queryable(tmp_path: Path) -> None:
    """Every owner writes its phase; the store persists and replays the sequence."""

    ledger, coordinator = _promote_to_delivery_ready(tmp_path)
    coordinator.transition(RUN_ID, "batch_checkpoint", "coordinator", expected_revision=ledger.get_revision(RUN_ID))
    coordinator.transition(RUN_ID, "all_slots_closed", "coordinator", expected_revision=ledger.get_revision(RUN_ID))
    coordinator.transition(RUN_ID, "readiness_passed", "coordinator", expected_revision=ledger.get_revision(RUN_ID))

    store = _store(tmp_path)
    sequence = [event["to"] for event in store.events()]
    assert sequence == ["research", "validation", "delivery"]
    assert store.current()["phase"] == "delivery"
    from research_tree.tree_state import tree_phase_of

    latest = CanonicalResearchTreeStateService(ledger).latest(round_id=RUN_ID, tree_id=TREE_ID)
    assert tree_phase_of(latest.payload) == "delivery"


def test_handoff_confirm_writes_compiled_birth_phase(tmp_path: Path) -> None:
    """The alignment handoff compile owns ``compiled``: explicit payload + store."""

    module = controller()
    module.init(tmp_path, "integration-run")
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    decision = module.plan(tmp_path, "integration-run", graph)
    module.confirm(
        tmp_path,
        "integration-run",
        "I accept the displayed strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )
    ledger = RunLedger(tmp_path / "ledger")
    ledger.create_run("round-alignment")
    tree = initialize_research_from_alignment(
        ledger,
        round_id="round-alignment",
        tree_id="research-tree",
        alignment_database=module.database_path(tmp_path, "integration-run"),
        expected_revision=ledger.get_revision("round-alignment"),
    )
    assert tree.payload["phase"] == DEFAULT_TREE_PHASE == "compiled"
    store = RunPhaseStore(run_phase_dir(ledger.workspace, "round-alignment"))
    assert store.current()["phase"] == "compiled"
    events = store.events()
    assert len(events) == 1
    assert events[0]["to"] == "compiled"
    assert events[0]["reason"]


def test_research_write_follows_the_confirmed_handoff(tmp_path: Path) -> None:
    """Tree initialization after a confirmed handoff advances compiled -> research."""

    module = controller()
    module.init(tmp_path, "integration-run")
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    decision = module.plan(tmp_path, "integration-run", graph)
    module.confirm(
        tmp_path,
        "integration-run",
        "I accept the displayed strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )
    ledger = RunLedger(tmp_path / "ledger")
    ledger.create_run("round-alignment")
    # The workflow already confirmed the handoff: autonomous research is live.
    ledger.append_artifact(
        "round-alignment",
        "run-state",
        RESEARCH_RUN_STATE_KIND,
        {"state": "autonomous_research"},
        expected_revision=ledger.get_revision("round-alignment"),
    )
    tree = initialize_research_from_alignment(
        ledger,
        round_id="round-alignment",
        tree_id="research-tree",
        alignment_database=module.database_path(tmp_path, "integration-run"),
        expected_revision=ledger.get_revision("round-alignment"),
    )
    # The returned artifact is the birth revision; the advance is queryable
    # through the canonical service.
    from research_tree.tree_state import tree_phase_of

    latest = CanonicalResearchTreeStateService(ledger).latest(round_id="round-alignment", tree_id="research-tree")
    assert tree_phase_of(latest.payload) == "research"
    assert latest.payload["phase"] == "research"
    assert latest.revision > tree.revision
    store = RunPhaseStore(run_phase_dir(ledger.workspace, "round-alignment"))
    assert [event["to"] for event in store.events()] == ["compiled", "research"]


def test_illegal_transitions_rejected_by_the_preexisting_gate(tmp_path: Path) -> None:
    """The #503 gate rejects writer shortcuts; nothing is persisted on refusal."""

    ledger, _coordinator = _promote_to_autonomous_research(tmp_path)
    service = CanonicalResearchTreeStateService(ledger)
    revision_before = ledger.get_revision(RUN_ID)
    store = _store(tmp_path)
    events_before = len(store.events())
    with pytest.raises(ResearchTreeStateError, match="illegal tree phase transition"):
        service.advance_phase(round_id=RUN_ID, tree_id=TREE_ID, phase="delivery", reason="shortcut")
    assert ledger.get_revision(RUN_ID) == revision_before
    assert len(store.events()) == events_before
    with pytest.raises(ResearchTreeStateError, match="illegal tree phase transition"):
        service.advance_phase(round_id=RUN_ID, tree_id=TREE_ID, phase="intake", reason="rewind")
    assert ledger.get_revision(RUN_ID) == revision_before


def test_reopen_reentry_writes_alignment_phase(tmp_path: Path) -> None:
    """The reopen-alignment re-entry is the owned writer of the alignment edge."""

    ledger, coordinator = _promote_to_autonomous_research(tmp_path)
    advanced = coordinator.reopen_alignment(RUN_ID, reason="user reopened alignment")
    assert advanced is not None
    from research_tree.tree_state import tree_phase_of

    latest = CanonicalResearchTreeStateService(ledger).latest(round_id=RUN_ID, tree_id=TREE_ID)
    assert tree_phase_of(latest.payload) == "alignment"
    store = _store(tmp_path)
    assert [event["to"] for event in store.events()] == ["research", "alignment"]
    # A same-phase reopen is a no-op, not a duplicate event.
    assert coordinator.reopen_alignment(RUN_ID, reason="repeat") is None
    assert len(store.events()) == 2


def test_hook_resolves_the_authoritative_phase_in_production(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No env var, no manifest phase: the store resolves research (gate live)."""

    ledger, coordinator = _promote_to_autonomous_research(tmp_path)
    coordinator.transition(RUN_ID, "batch_checkpoint", "coordinator", expected_revision=ledger.get_revision(RUN_ID))
    _write_manifest(tmp_path)
    monkeypatch.delenv("RESEARCH_TREE_RUN_PHASE", raising=False)
    monkeypatch.delenv("RESEARCH_TREE_PROJECT_ID", raising=False)
    monkeypatch.delenv("RESEARCH_TREE_RUN_ID", raising=False)

    result = _submit(tmp_path, "so anyway, how about that local sports team")
    assert result["status"] == "recorded"
    assert result["run_phase"] == "research"
    # The chatty prompt matches no re-entry rule: refused under research.
    assert result["reentry"]["path"] == "refused"
    assert result["reentry"]["code"] == "research_reentry_refused"


def test_reentry_gate_activates_only_in_research(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside research the two-option protocol is inert; inside, it governs."""

    _write_manifest(tmp_path)
    monkeypatch.delenv("RESEARCH_TREE_RUN_PHASE", raising=False)
    store = _store(tmp_path)
    chatty = "so anyway, how about that local sports team"

    store.record_transition(phase="alignment", reason="alignment_started")
    result = _submit(tmp_path, chatty)
    assert result["run_phase"] == "alignment"
    assert "reentry" not in result

    store.record_transition(phase="research", reason="handoff_confirmed")
    result = _submit(tmp_path, chatty)
    assert result["run_phase"] == "research"
    assert result["reentry"]["path"] == "refused"


def test_hook_falls_back_when_the_store_is_absent_or_tampered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing or digest-broken store degrades fail-open, never to a wrong phase."""

    _write_manifest(tmp_path)
    monkeypatch.delenv("RESEARCH_TREE_RUN_PHASE", raising=False)
    monkeypatch.setenv("RESEARCH_TREE_RUN_PHASE", "validation")
    result = _submit(tmp_path, "status?")
    assert result["run_phase"] == "validation"

    monkeypatch.delenv("RESEARCH_TREE_RUN_PHASE", raising=False)
    store = _store(tmp_path)
    store.record_transition(phase="research", reason="handoff_confirmed")
    state = json.loads(store.state_path.read_text(encoding="utf-8"))
    state["phase"] = "delivery"  # tamper: payload no longer matches the digest
    store.state_path.write_text(json.dumps(state), encoding="utf-8")
    result = _submit(tmp_path, "status?")
    assert "run_phase" not in result


def test_plan_under_research_redirects_to_the_reopen_path(tmp_path: Path) -> None:
    """Under research the graph refuses new asks; the redirect names reopen."""

    module = controller()
    module.init(tmp_path, RUN_ID)
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    decision = module.plan(tmp_path, RUN_ID, graph)
    store = _store(tmp_path)
    store.record_transition(phase="research", reason="handoff_confirmed")

    redirected = module.plan(tmp_path, RUN_ID, graph)
    assert redirected["action"] == "reopen_alignment"
    assert redirected["run_phase"] == "research"
    assert "reopen" in redirected["reason"].lower()
    assert redirected["question"] is None
    # No alignment turn was consumed and no ask was selected.
    assert redirected["turn"] == decision["turn"]
    assert module.AlignmentGraphStore(module.database_path(tmp_path, RUN_ID)).status()["controller"]["plan_count"] == 1
    assert decision["action"] != "reopen_alignment"


def test_record_under_research_phase_is_refused(tmp_path: Path) -> None:
    """Recording an alignment outcome under research is a protocol violation."""

    module = controller()
    module.init(tmp_path, RUN_ID)
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    module.plan(tmp_path, RUN_ID, graph)
    store = _store(tmp_path)
    store.record_transition(phase="research", reason="handoff_confirmed")
    with pytest.raises(AlignmentGraphError, match="research"):
        module.record(tmp_path, RUN_ID, "goal", "changed", "fingerprint-1")


def test_exactly_one_event_statement_per_transition_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The statement is appended once at the transition; the hook announces it once."""

    _write_manifest(tmp_path)
    monkeypatch.delenv("RESEARCH_TREE_RUN_PHASE", raising=False)
    store = _store(tmp_path)
    store.record_transition(phase="alignment", reason="alignment_started")
    assert len(store.events()) == 1

    first = _submit(tmp_path, "status?")
    grounding = first["phase_grounding"]
    assert set(grounding) == {"snapshot", "events"}
    assert grounding["events"] == ["run-phase: start -> alignment (alignment_started)"]

    store.record_transition(phase="compiled", reason="alignment_handoff_confirmed")
    assert len(store.events()) == 2
    second = _submit(tmp_path, "status?")
    assert second["phase_grounding"]["events"] == ["run-phase: alignment -> compiled (alignment_handoff_confirmed)"]

    # No rebroadcast: the statement entered history once, at its own transition.
    third = _submit(tmp_path, "status?")
    assert third["phase_grounding"]["events"] == []

    store.record_transition(phase="research", reason="handoff_confirmed")
    fourth = _submit(tmp_path, "status?")
    assert fourth["phase_grounding"]["events"] == ["run-phase: compiled -> research (handoff_confirmed)"]


def test_snapshot_line_is_single_line_and_order_stable(tmp_path: Path) -> None:
    """Fixed slots, fixed order, one line, digest-bound to the store."""

    store = _store(tmp_path)
    placeholder = build_phase_snapshot(None)
    assert placeholder == "phase=unknown stance=S0 viol=0 topics=0 digest=none"

    state = store.record_transition(phase="research", reason="handoff_confirmed")
    line = build_phase_snapshot(store.current())
    assert "\n" not in line
    fields = line.split(" ")
    assert [field.split("=")[0] for field in fields] == ["phase", "stance", "viol", "topics", "digest"]
    assert line == "phase=research stance=S0 viol=0 topics=0 digest=" + state["digest"][:12]
    # Order-stable across repeated reads of unchanged state.
    assert build_phase_snapshot(store.current()) == line
    # A changed phase moves exactly its own slot.
    store.record_transition(phase="validation", reason="validation_started")
    moved = build_phase_snapshot(store.current())
    assert moved.startswith("phase=validation stance=S0 viol=0 topics=0 digest=")


def test_render_phase_event_is_a_single_stable_line() -> None:
    statement = render_phase_event({"from": "compiled", "to": "research", "reason": "handoff_confirmed"})
    assert statement == "run-phase: compiled -> research (handoff_confirmed)"
    assert "\n" not in statement


def _write_manifest(tmp_path: Path, run_id: str = RUN_ID) -> None:
    manifest_dir = tmp_path / ".research-tree" / "projects" / f"alignment-{run_id}" / "runs" / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"project_id": f"alignment-{run_id}", "run_id": run_id}),
        encoding="utf-8",
    )
