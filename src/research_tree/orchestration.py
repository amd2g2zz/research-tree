"""Compile depth-oriented worker waves for autonomous research portfolios.

The artifact scheduler decides which persisted Work Items may start now.  This
module decides how each consequential Work Item should be investigated over
time: broad orientation, decision-specific depth, adversarial checking, and
validation.  It is intentionally pure so hosts can execute the waves with
Codex, Claude Code, Hermes, or another worker runtime.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .insights import synthesize_insights


RESEARCH_PHASES = ("landscape", "deep_dive", "adversarial", "validation")
ACTIVE_STATUSES = {"planned", "ready", "running"}
EXECUTION_STATES = {"planned", "ready", "running", "drained", "blocked", "failed"}


def compile_orchestration_plan(
    works: Sequence[Any],
    slots: Mapping[str, Mapping[str, Any]],
    scores: Mapping[str, Mapping[str, Any]],
    *,
    max_parallelism: int,
    initial_dispatch_ids: Sequence[str],
) -> dict[str, Any]:
    """Return a deterministic, multi-pass worker plan.

    A phase is a worker assignment, not a source-count requirement.  The
    phase's evidence standard and completion oracle determine when it closes.
    Dependencies are carried from the persisted Work Item graph and extended
    so validation cannot run before depth and adversarial checks.
    """

    by_id = {work.id: work for work in works}
    active = {
        work.id
        for work in works
        if str(work.payload.get("status", "")) in ACTIVE_STATUSES
    }
    dependencies = {
        work.id: tuple(work.payload.get("depends_on", ()))
        for work in works
    }
    phase_tasks: dict[str, dict[str, Any]] = {}
    for work in works:
        slot = slots.get(str(work.payload.get("decision_slot_id")), {})
        priority = str(slot.get("priority", "P1"))
        required = _required_phases(slot, priority)
        for phase in required:
            task_id = _task_id(work.id, phase)
            phase_dependencies = list(
                _task_id(dependency, "validation") for dependency in dependencies[work.id]
            )
            if phase == "deep_dive" or phase == "adversarial":
                phase_dependencies.append(_task_id(work.id, "landscape"))
            elif phase == "validation":
                phase_dependencies.extend(
                    (_task_id(work.id, "deep_dive"), _task_id(work.id, "adversarial"))
                )
            elif phase == "landscape":
                phase_dependencies = list(phase_dependencies)
            phase_tasks[task_id] = {
                "task_id": task_id,
                "work_item_id": work.id,
                "decision_slot_id": str(work.payload.get("decision_slot_id")),
                "phase": phase,
                "priority": priority,
                "depends_on": sorted(set(phase_dependencies)),
                "objective": _objective(phase, work, slot),
                "evidence_standard": _evidence_standard(phase, work, slot),
                "completion_rule": _completion_rule(phase, work, slot),
                "status": (
                    "running"
                    if work.payload.get("status") == "running" and phase == "landscape"
                    else "planned"
                    if work.id in active
                    else str(work.payload.get("status"))
                ),
            }

    waves: list[dict[str, Any]] = []
    remaining = {
        task_id for task_id, task in phase_tasks.items() if task["status"] in {"planned", "ready"}
    }
    wave_number = 1
    while remaining:
        ready = sorted(
            task_id
            for task_id in remaining
            if set(phase_tasks[task_id]["depends_on"]).isdisjoint(remaining)
        )
        if not ready:
            raise ValueError("orchestration phase graph contains a cycle")
        selected = ready[:max_parallelism]
        for task_id in selected:
            phase_tasks[task_id]["status"] = "scheduled"
        waves.append(
            {
                "wave": wave_number,
                "phase": _common_phase(selected, phase_tasks),
                "task_ids": selected,
                "work_item_ids": sorted({phase_tasks[item]["work_item_id"] for item in selected}),
                "reason": "Ready after predecessor evidence and bounded by worker capacity.",
            }
        )
        remaining.difference_update(selected)
        wave_number += 1

    p0_slots = sorted(
        str(work.payload.get("decision_slot_id"))
        for work in works
        if str(work.payload.get("decision_slot_id")) in slots
        and str(slots[str(work.payload.get("decision_slot_id"))].get("priority")) == "P0"
        and work.id in active
    )
    covered_slots = sorted({task["decision_slot_id"] for task in phase_tasks.values()})
    required_phases = {
        slot_id: list(_required_phases(slots[slot_id], str(slots[slot_id].get("priority", "P1"))))
        for slot_id in covered_slots
    }
    scheduled_phases = {
        slot_id: sorted(
            task["phase"] for task in phase_tasks.values() if task["decision_slot_id"] == slot_id
        )
        for slot_id in covered_slots
    }
    uncovered = sorted(
        slot_id
        for slot_id, phases in required_phases.items()
        if set(phases) - set(scheduled_phases.get(slot_id, ()))
    )
    initial_capacity = min(max_parallelism, len(initial_dispatch_ids))
    completed_initial = {
        task_id
        for task_id, task in phase_tasks.items()
        if by_id[task["work_item_id"]].payload.get("status") == "complete"
    }
    blocked_initial = {
        task_id
        for task_id, task in phase_tasks.items()
        if by_id[task["work_item_id"]].payload.get("status") in {"cancelled", "deferred"}
    }
    running_initial = {
        task_id for task_id, task in phase_tasks.items() if task["status"] == "running"
    }
    return {
        "mode": "deep_research",
        "phase_order": list(RESEARCH_PHASES),
        "waves": waves,
        "tasks": [phase_tasks[task_id] for task_id in sorted(phase_tasks)],
        "coverage": {
            "p0_decision_slot_ids": p0_slots,
            "required_phases": required_phases,
            "scheduled_phases": scheduled_phases,
            "uncovered_decision_slot_ids": uncovered,
            "closure_rule": (
                "Do not compile final delivery until every active P0 slot has a completed "
                "Finding Pack, counterevidence result, and validation oracle."
            ),
        },
        "worker_utilization": {
            "available_parallelism": max_parallelism,
            "initial_dispatch_count": len(initial_dispatch_ids),
            "initial_capacity_used": initial_capacity,
            "underused": bool(initial_dispatch_ids) and initial_capacity < min(max_parallelism, len(active)),
            "underuse_reason": (
                "Dependencies, terminal work, or duplicate suppression limited the ready set."
                if initial_capacity < min(max_parallelism, len(active))
                else "All currently independent work was dispatched up to capacity."
            ),
        },
        "execution": advance_execution(
            {"tasks": list(phase_tasks.values())},
            completed_task_ids=sorted(completed_initial),
            blocked_task_ids=sorted(blocked_initial),
            running_task_ids=sorted(running_initial),
            max_parallelism=max_parallelism,
        ),
        "insights": synthesize_insights(
            (),
            active_slot_ids=sorted(
                {
                    str(work.payload.get("decision_slot_id"))
                    for work in works
                    if work.id in active and work.payload.get("decision_slot_id")
                }
            ),
        ),
        "next_action": "execute_wave_1_then_replan_after_finding_pack_ingestion",
    }


def validate_orchestration_plan(value: Mapping[str, Any]) -> None:
    """Validate the scheduler's depth projection without validating prose."""

    required = {
        "mode",
        "phase_order",
        "waves",
        "tasks",
        "coverage",
        "worker_utilization",
        "execution",
        "insights",
        "next_action",
    }
    if set(value) != required:
        raise ValueError(
            f"orchestration has unexpected keys; missing={sorted(required - set(value))}, "
            f"extra={sorted(set(value) - required)}"
        )
    if value.get("mode") != "deep_research":
        raise ValueError("orchestration.mode must be deep_research")
    if tuple(value.get("phase_order", ())) != RESEARCH_PHASES:
        raise ValueError("orchestration.phase_order must preserve the research phase order")
    for key in ("waves", "tasks"):
        if not isinstance(value.get(key), Sequence) or isinstance(value.get(key), (str, bytes)):
            raise ValueError(f"orchestration.{key} must be a sequence")
    if not isinstance(value.get("coverage"), Mapping):
        raise ValueError("orchestration.coverage must be a mapping")
    if not isinstance(value.get("worker_utilization"), Mapping):
        raise ValueError("orchestration.worker_utilization must be a mapping")
    if not isinstance(value.get("insights"), Mapping):
        raise ValueError("orchestration.insights must be a mapping")
    execution = value.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("orchestration.execution must be a mapping")
    if execution.get("state") not in EXECUTION_STATES:
        raise ValueError("orchestration.execution.state is unsupported")
    for key in ("ready_task_ids", "running_task_ids", "completed_task_ids", "failed_task_ids", "blocked_task_ids"):
        if not isinstance(execution.get(key), Sequence) or isinstance(execution.get(key), (str, bytes)):
            raise ValueError(f"orchestration.execution.{key} must be a sequence")


def advance_execution(
    plan: Mapping[str, Any],
    *,
    completed_task_ids: Sequence[str] = (),
    failed_task_ids: Sequence[str] = (),
    blocked_task_ids: Sequence[str] = (),
    running_task_ids: Sequence[str] = (),
    max_parallelism: int | None = None,
) -> dict[str, Any]:
    """Advance a plan-to-execute drain loop by one deterministic batch.

    Worker results are supplied as task IDs, so a host can persist raw Finding
    Packs separately and call this function after ingestion.  Failed or blocked
    predecessors never disappear: dependants are surfaced as blocked and the
    coordinator can replan them with a new Work Item or evidence event.
    """

    raw_tasks = plan.get("tasks")
    if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes)):
        raise ValueError("plan.tasks must be a sequence")
    tasks = {str(task["task_id"]): task for task in raw_tasks if isinstance(task, Mapping)}
    if len(tasks) != len(raw_tasks):
        raise ValueError("plan.tasks must contain unique mappings")
    all_ids = set(tasks)
    completed = set(completed_task_ids)
    failed = set(failed_task_ids)
    blocked = set(blocked_task_ids)
    running = set(running_task_ids)
    for label, values in (("completed", completed), ("failed", failed), ("blocked", blocked), ("running", running)):
        unknown = values - all_ids
        if unknown:
            raise ValueError(f"execution {label} references unknown task ids: {sorted(unknown)}")
    overlap = (completed & failed) | (completed & blocked) | (failed & blocked)
    if overlap:
        raise ValueError("execution result sets must not overlap")
    if max_parallelism is None:
        max_parallelism = len(tasks) or 1
    if isinstance(max_parallelism, bool) or max_parallelism < 1:
        raise ValueError("max_parallelism must be positive")
    terminal = completed | failed | blocked
    for task_id, task in tasks.items():
        dependencies = set(task.get("depends_on", ()))
        unknown = dependencies - all_ids
        if unknown:
            raise ValueError(f"task {task_id} depends on unknown tasks: {sorted(unknown)}")
        if task_id in terminal or task_id in running:
            continue
        if dependencies & (failed | blocked):
            blocked.add(task_id)
    terminal = completed | failed | blocked
    ready = sorted(
        task_id
        for task_id, task in tasks.items()
        if task_id not in terminal
        and task_id not in running
        and set(task.get("depends_on", ())).issubset(completed)
    )
    limit = max_parallelism - len(running)
    if limit < 0:
        raise ValueError("running tasks exceed max_parallelism")
    dispatch = ready[:limit]
    remaining = all_ids - terminal - running - set(dispatch)
    if dispatch or running:
        state = "running"
    elif blocked and not remaining:
        state = "blocked"
    elif not remaining:
        state = "drained"
    else:
        state = "ready"
    return {
        "state": state,
        "ready_task_ids": ready,
        "dispatch_task_ids": dispatch,
        "running_task_ids": sorted(running | set(dispatch)),
        "completed_task_ids": sorted(completed),
        "failed_task_ids": sorted(failed),
        "blocked_task_ids": sorted(blocked),
        "remaining_task_ids": sorted(remaining),
        "transition": "plan->execute->ingest->replan",
    }


def _required_phases(slot: Mapping[str, Any], priority: str) -> tuple[str, ...]:
    """Use decision consequence to choose depth, never a fixed source count."""

    if priority == "P0" or str(slot.get("uncertainty")) == "high":
        return RESEARCH_PHASES
    if slot.get("repository_touchpoints") or slot.get("validation"):
        return ("landscape", "deep_dive", "validation")
    return ("landscape", "deep_dive", "adversarial")


def _task_id(work_id: str, phase: str) -> str:
    return f"{work_id}@{phase}"


def _common_phase(task_ids: Sequence[str], tasks: Mapping[str, Mapping[str, Any]]) -> str:
    phases = {str(tasks[item]["phase"]) for item in task_ids}
    return next(iter(phases)) if len(phases) == 1 else "mixed"


def _objective(phase: str, work: Any, slot: Mapping[str, Any]) -> str:
    question = str(work.payload.get("scope", slot.get("question", "")))
    return {
        "landscape": f"Map the current evidence landscape for: {question}",
        "deep_dive": f"Resolve the decision-specific evidence gap for: {question}",
        "adversarial": f"Search for counterevidence, failure modes, and disconfirming cases for: {question}",
        "validation": f"Validate the leading option against the stated oracle for: {question}",
    }[phase]


def _evidence_standard(phase: str, work: Any, slot: Mapping[str, Any]) -> str:
    base = str(slot.get("evidence_standard", "decision-specific evidence with provenance"))
    if phase == "landscape":
        return f"{base}; identify primary sources, repository anchors, and unknowns"
    if phase == "deep_dive":
        return f"{base}; inspect the decisive primary or repository evidence in full"
    if phase == "adversarial":
        return f"{base}; include an explicit counterevidence search and negative result when applicable"
    return f"{base}; execute or independently inspect the stated validation oracle"


def _completion_rule(phase: str, work: Any, slot: Mapping[str, Any]) -> str:
    if phase == "landscape":
        return "Return a Finding Pack with candidate options, source map, and unresolved gaps."
    if phase == "deep_dive":
        return "Return atomic findings with provenance, applicability, confidence, and option effects."
    if phase == "adversarial":
        return "Return counterevidence, failed approaches, or an explicit searched-without-result record."
    return str(slot.get("validation", {}).get("oracle", work.payload.get("completion_rule", "")))
