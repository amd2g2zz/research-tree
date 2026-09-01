"""Live-host failure-injection matrix for issue #292 gate 7.

Six failure scenarios x three admitted hosts.  Every cell drives a real
research-tree runtime run to its injection point (RunLedger + coordinator +
project workspace), injects the failure through the runtime's existing
failure-handling path, observes the disposition, and records one canonical
receipt cell.  No runtime component is replaced by a stand-in: injection goes
through public entry points (host-event ingestion, real CAS byte mutation, the
run-bound launcher subprocess, and the host-neutral CLI).

Live/simulated vocabulary (honest provenance, never overstated):
- a cell is ``live`` when its whole chain (setup -> inject -> observe) executes
  real runtime code on real files, subprocesses, and ledgers;
- ``cause`` records where the failure originates: ``runtime-internal`` (the
  injection is a real runtime/file state), ``synthesized-trigger`` (an external
  cause is declared through the runtime's real declaration path), or
  ``runtime-cli`` (the failure is injected through the CLI);
- ``host_process_invoked`` is False in this environment for every cell: no
  third-party host product binary is in the loop, and every receipt says so.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from research_tree.cli import main as cli_main
from research_tree.completion_inputs import CompletionInputRegistrar
from research_tree.coordinator import (
    HOST_EVENT_KIND,
    CoordinatorConflictError,
    ResearchRunCoordinator,
)
from research_tree.decision_frame import DecisionFrame, IntentHypothesis
from research_tree.domain import ArtifactRef
from research_tree.host_attempts import (
    classify_attempt,
    normalize_attempt,
    worker_finished_eligible,
)
from research_tree.host_events import HostEvent, payload_digest
from research_tree.run_ledger import RunLedger
from research_tree.strategy_projection import StrategyProjection, authority_fingerprint

SCENARIOS: tuple[str, ...] = (
    "interruption",
    "provider_error",
    "stale_child",
    "artifact_tamper",
    "resume",
    "cross_workspace_isolation",
)
HOSTS: tuple[str, ...] = ("codex", "claude", "hermes")

# Matrix host name -> host identity the runtime admits in attempt outcomes
# (research_tree.host_attempts.HOST_ATTEMPT_HOSTS).
ATTEMPT_HOSTS: Mapping[str, str] = {"codex": "codex", "claude": "claude-code", "hermes": "hermes"}

# Per-host SubagentStop event name.  The run-bound launcher binds identity only
# for the Claude-style name that codex and claude share; hermes emits
# snake_case events, so its launcher record carries no binding_status.  This
# per-host injectability asymmetry is recorded in receipts, not papered over.
_LAUNCHER_EVENT_NAMES: Mapping[str, str] = {
    "codex": "SubagentStop",
    "claude": "SubagentStop",
    "hermes": "subagent_stop",
}

_CASE_ID = "host-matrix-v1"
_CASE_ID_SUBSET = f"{_CASE_ID}-subset"


@dataclass(frozen=True)
class CellResult:
    """One scenario x host cell: setup, injection, disposition, verdict."""

    scenario: str
    host: str
    status: str
    injection_transport: str
    cause: str
    host_process_invoked: bool
    expected_reason: str
    observed_reason: str
    false_completion: bool
    state_mutated: bool
    detail: str
    events: tuple[str, ...]
    identities: tuple[str, ...]
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class _Injection:
    """One observed injection: canonical token plus whether it matched."""

    token: str
    matched: bool
    message: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _observe(
    action: Callable[[], Any], *, token: str, marker: str, errors: tuple[type[BaseException], ...]
) -> _Injection:
    """Run one injection and record whether the runtime disposition matched."""

    try:
        action()
    except errors as error:
        return _Injection(token, marker in str(error), str(error))
    except Exception as error:  # harness must observe any disposition, never crash the cell
        return _Injection(token, False, f"unexpected {type(error).__name__}: {error}")
    return _Injection(token, False, "no rejection raised")


def _capture_cli(argv: list[str]) -> tuple[int, dict[str, Any]]:
    """Invoke the real CLI entry point and parse the emitted JSON envelope."""

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_main(argv)
    text = buffer.getvalue()
    try:
        envelope = json.loads(text[text.index("{") : text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as error:
        raise CoordinatorConflictError(f"cli_output_unparseable: {text!r}") from error
    return code, envelope


def _joined(outcomes: list[_Injection]) -> str:
    """Join observation tokens; unmatched ones stay visible for diagnosis."""

    return "+".join(item.token if item.matched else f"UNMATCHED({item.message})" for item in outcomes)


def _observe_immutable(
    action: Callable[[], Any],
    ledger: RunLedger,
    run_id: str,
    *,
    token: str,
    marker: str,
    errors: tuple[type[BaseException], ...],
) -> tuple[_Injection, bool]:
    """Observe one rejection and whether it mutated canonical run state."""

    before = ledger.get_revision(run_id)
    injection = _observe(action, token=token, marker=marker, errors=errors)
    return injection, ledger.get_revision(run_id) != before


# --- runtime run preparation -------------------------------------------------


def _event(
    ledger: RunLedger,
    *,
    event_id: str,
    kind: str,
    run_id: str,
    attempt_id: str,
    sequence: int,
    payload: Mapping[str, Any],
    causation_id: str | None = None,
    expected_revision: int | None = None,
    actor: str = "worker",
) -> HostEvent:
    return HostEvent.from_value(
        {
            "event_id": event_id,
            "kind": kind,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "expected_revision": ledger.get_revision(run_id) if expected_revision is None else expected_revision,
            "sequence": sequence,
            "actor": actor,
            "created_at": _now(),
            "causation_id": causation_id,
            "payload": dict(payload),
            "payload_digest": payload_digest(payload),
        }
    )


def _append(ledger: RunLedger, run_id: str, artifact_id: str, kind: str, payload: Mapping[str, Any], parents=()):
    return ledger.append_artifact(
        run_id,
        artifact_id,
        kind,
        dict(payload),
        parent_refs=parents,
        expected_revision=ledger.get_revision(run_id),
    )


def _prepare_strategy_confirmation(ledger: RunLedger, coordinator: ResearchRunCoordinator, run_id: str) -> None:
    """Drive the real coordinator from handoff to confirmed autonomous research."""

    artifacts = ledger.load_run(run_id).artifacts
    handoff = next(item for item in artifacts if item.kind == "alignment-handoff")
    target = next(item for item in artifacts if item.kind == "blueprint-target")
    target_ref = ArtifactRef(run_id, target.id, target.revision)
    frame = DecisionFrame.create(
        frame_id=f"frame-{run_id}",
        run_id=run_id,
        requester_wording="Choose the customer decision to validate.",
        primary_decision={
            "id": "decision-1",
            "statement": "Choose the customer decision",
            "success_signal": "The payer and validation signal are explicit",
        },
        target_ref=target_ref,
        hypotheses=(
            IntentHypothesis(
                id="selected",
                interpretation="The selected customer decision",
                ambiguity="The choice is now explicit",
                owner="requester",
                researchable=False,
                decision_consequence="sets the research scope",
                source_refs=(f"input-{run_id}",),
                disposition="selected",
                next_action="form strategy",
                primary_decision_id="decision-1",
                material=True,
                evidence_ranked=True,
            ),
        ),
    )
    frame_artifact = coordinator.persist_decision_frame(frame, expected_revision=ledger.get_revision(run_id))
    projection = StrategyProjection.create(
        projection_id=f"strategy-{run_id}",
        run_id=run_id,
        decision_frame_ref=ArtifactRef(run_id, frame_artifact.id, frame_artifact.revision),
        alignment_handoff_ref=ArtifactRef(run_id, handoff.id, handoff.revision),
        target_ref=target_ref,
        current_understanding="Validate the requester decision.",
        assumptions=("requester owns outcome",),
        decision_targets=("decision-1",),
        tracks=({"id": "track-1"},),
        method_hypotheses=({"method": "repository"},),
        depth="deep",
        evidence_expectations=("independent source",),
        autonomy_envelope={"allowed": ["research"]},
        replanning_policy={"same_round": ["depth"]},
        success_oracles=({"id": "oracle-1", "evidence_standard_ids": ("standard-1",)},),
        delivery_contract={"technical": "package", "human": "report"},
        stop_rule="oracles pass",
        preference_influences=(),
        revision=1,
        status="displayed",
    )
    coordinator.persist_strategy_projection(projection, expected_revision=ledger.get_revision(run_id))
    # Issue #462: the display gate requires an independent subagent alignment
    # verification bound to the projection content before display.
    CompletionInputRegistrar(ledger).write_alignment_verification(
        round_id=run_id,
        verification_id=f"alignment-verification-{run_id}",
        payload={
            "schema": 1,
            "id": f"alignment-verification-{run_id}",
            "round_id": run_id,
            "projection_ref": {
                "round_id": run_id,
                "artifact_id": projection.projection_id,
                "revision": projection.revision,
            },
            "authority_fingerprint": authority_fingerprint(projection),
            "verifier_identity": "agent-verifier-harness",
            "session_context": "session-harness-main",
            "understood": {
                "outcome": "Independently restated: validate the requester decision.",
                "scope": "Independently restated: research only.",
                "authority": "Independently restated: autonomous research within the envelope.",
                "success_oracles": [{"id": "oracle-1", "understanding": "Independently restated oracle oracle-1."}],
            },
            "discrepancies": [],
        },
        expected_revision=ledger.get_revision(run_id),
    )
    coordinator.display_strategy(run_id, projection, expected_revision=ledger.get_revision(run_id))
    coordinator.confirm_handoff(
        run_id,
        projection_ref=ArtifactRef(run_id, projection.id, projection.revision),
        confirmation=(
            f"I accept {projection.display_digest} authority-fingerprint {authority_fingerprint(projection)} "
            "and authorize research."
        ),
        expected_revision=ledger.get_revision(run_id),
    )


def _prepare_run(workspace: Path, host: str, label: str) -> tuple[RunLedger, ResearchRunCoordinator, Any, str]:
    """Create a real run driven to a dispatched, active attempt lease."""

    workspace.mkdir(parents=True, exist_ok=True)
    run_id = f"run-{host}-{label}"
    ledger = RunLedger(workspace)
    ledger.create_run(run_id)
    handoff = _append(ledger, run_id, f"handoff-{label}", "alignment-handoff", {"confirmed": True})
    target = _append(
        ledger,
        run_id,
        f"target-{label}",
        "blueprint-target",
        {"decision_slots": [{"id": "slot-1", "priority": "P0", "closure_oracle": "oracle-1"}]},
        (ArtifactRef(run_id, handoff.id, handoff.revision),),
    )
    coordinator = ResearchRunCoordinator(ledger)
    coordinator.initialize(
        run_id=run_id,
        alignment_handoff=handoff,
        blueprint_target=target,
        expected_revision=ledger.get_revision(run_id),
    )
    _prepare_strategy_confirmation(ledger, coordinator, run_id)
    lease = coordinator.dispatch(
        run_id=run_id,
        work_item={"objective": f"observe {label}", "success_oracle": "coordinator verifies"},
        worker_id=f"worker-{host}",
        expected_revision=ledger.get_revision(run_id),
        attempt_id=f"attempt-{host}-{label}",
    )
    return ledger, coordinator, lease, run_id


def _persisted_events(ledger: RunLedger, run_id: str) -> list[tuple[str, str]]:
    return [
        (str(item.payload.get("kind")), str(item.payload.get("attempt_id")))
        for item in ledger.load_run(run_id).artifacts
        if item.kind == HOST_EVENT_KIND
    ]


def _canonical_events(ledger: RunLedger, run_id: str) -> tuple[str, ...]:
    return tuple(f"{kind}:{attempt}" for kind, attempt in _persisted_events(ledger, run_id))


def _false_completion(ledger: RunLedger, run_id: str) -> bool:
    return any(kind == "worker_finished" for kind, _attempt in _persisted_events(ledger, run_id))


def _attempt_outcome(host: str, attempt_id: str, **overrides) -> dict[str, Any]:
    values: dict[str, Any] = {
        "process_exit": None,
        "timed_out": False,
        "provider_disposition": None,
        "usage_disposition": None,
        "expected_deliverables": ("report",),
        "observed_deliverables": (),
        "host_id": ATTEMPT_HOSTS[host],
        "session_id": f"session-{host}",
        "attempt_id": attempt_id,
    }
    values.update(overrides)
    outcome = normalize_attempt(**values)
    return {
        "dict": outcome.to_dict(),
        "classification": classify_attempt(outcome),
        "eligible": worker_finished_eligible(outcome),
    }


_SCENARIOS: Mapping[str, Callable[[str, Path], CellResult]] | None = None


def _scenario_handlers() -> Mapping[str, Callable[[str, Path], CellResult]]:
    """Resolve the scenario dispatch table lazily to avoid an import cycle."""

    global _SCENARIOS
    if _SCENARIOS is None:
        from host_matrix_cells import SCENARIO_HANDLERS

        _SCENARIOS = SCENARIO_HANDLERS
    return _SCENARIOS


def run_scenario(scenario: str, host: str, workspace: Path) -> CellResult:
    """Execute one scenario x host cell against a real run in ``workspace``."""

    handler = _scenario_handlers().get(scenario)
    if handler is None:
        raise KeyError(f"unsupported matrix scenario: {scenario} (expected one of {SCENARIOS})")
    if host not in HOSTS:
        raise KeyError(f"unsupported matrix host: {host} (expected one of {HOSTS})")
    return handler(host, workspace)


def build_receipt(cells: list[CellResult]) -> dict[str, Any]:
    """Project cell results onto the harness receipt contract (host-conformance shape).

    The receipt asserts only what this harness observed: no replay evidence is
    produced here, so no ``replay`` key is emitted (omitting the optional field
    is the honest form under ``host-conformance-result-v1``).  ``coverage`` and
    the conditioned ``case_id`` keep a subset run distinguishable from a full
    6x3 matrix execution.
    """

    cells = sorted(cells, key=lambda item: (SCENARIOS.index(item.scenario), HOSTS.index(item.host)))
    executed_scenarios = sorted({cell.scenario for cell in cells}, key=SCENARIOS.index)
    executed_hosts = sorted({cell.host for cell in cells}, key=HOSTS.index)
    expected_cells = len(SCENARIOS) * len(HOSTS)
    is_complete = (
        bool(cells)
        and {cell.scenario for cell in cells} == set(SCENARIOS)
        and {cell.host for cell in cells} == set(HOSTS)
        and len(cells) == expected_cells
    )
    receipt_cells = [
        {
            "name": f"{cell.scenario}:{cell.host}",
            "status": cell.status,
            "detail": cell.detail,
            "identities": list(cell.identities),
            "events": list(cell.events),
            "matrix": {
                "scenario": cell.scenario,
                "host": cell.host,
                "injection_transport": cell.injection_transport,
                "cause": cell.cause,
                "host_process_invoked": cell.host_process_invoked,
                "expected_reason": cell.expected_reason,
                "observed_reason": cell.observed_reason,
                "false_completion": cell.false_completion,
                "state_mutated": cell.state_mutated,
                "evidence": dict(cell.evidence),
            },
        }
        for cell in cells
    ]
    return {
        "schema_version": 1,
        "case_id": _CASE_ID if is_complete else _CASE_ID_SUBSET,
        "mode": cells[0].host if len(executed_hosts) == 1 else "host-matrix",
        "status": "passed" if cells and all(cell.status == "passed" for cell in cells) else "failed",
        "cells": receipt_cells,
        "coverage": {
            "scenarios": len(executed_scenarios),
            "hosts": len(executed_hosts),
            "cells": len(cells),
            "expected_cells": expected_cells,
            "complete": is_complete,
        },
        "blocker": None if cells else "no cells executed",
        "matrix": {
            "scenarios": executed_scenarios,
            "hosts": executed_hosts,
            "host_process_invoked": False,
            "live_vs_simulated": (
                "all cells execute live runtime failure paths (real ledgers, files, launcher subprocess, CLI); "
                "no third-party host product binary is invoked; cells whose external cause is declared through "
                "a runtime declaration path carry cause=synthesized-trigger rather than being marked simulated"
            ),
        },
    }


def run_matrix(
    workspace: Path,
    *,
    hosts: tuple[str, ...] = HOSTS,
    scenarios: tuple[str, ...] = SCENARIOS,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Run the scenario x host matrix and return the canonical receipt."""

    cells = [run_scenario(scenario, host, workspace) for host in hosts for scenario in scenarios]
    receipt = build_receipt(cells)
    if result_path is not None:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return receipt
