# ADR-006: Single Scheduling Authority

- Status: accepted (2026-08-30)
- Deciders: maintainer; alpha3 batch 1 planning session (issue #333)
- Related: ADR-002 (single completion authority), issue #333

## Context

Three scheduling layers accumulated across cycles:

| Layer | State at 0aa67a7 | Disposition |
|---|---|---|
| `orchestration.py` (358 lines, 4-phase wave compiler) | Dead: only consumer was the `__init__` re-export; tests never imported `compile_orchestration_plan` | **Retired (deleted)** |
| `policy.py` / `AdaptiveResearchPolicy` (~564 lines) | Live, no production wiring — tests only | **Wired into `coordinator.dispatch`** |
| `coordinator.py::dispatch` | Production path (CLI + tests) | **The single scheduling authority** |

## Decision

1. `orchestration.py` is deleted outright — no deprecation cycle. Precedent:
   `scheduler.py` purge (ad0356d). Repo-wide grep at deletion time showed zero
   consumers outside the `__init__` re-export; `tests/test_worker_orchestration.py`
   exercises work-item wave semantics on the coordinator, not the deleted module.
2. `AdaptiveResearchPolicy` enters the production path at the dispatch
   strategy-projection confirmation point: `ResearchRunCoordinator.__init__`
   accepts an optional `policy`; when wired, dispatch derives decision-slot
   deficits, consults `policy.evaluate(slots=...)`, and records the top
   proposal's `action_id` as `policy_proposal_id` in the lease payload (attempt
   lineage). No policy wired, or nothing proposed → `policy_proposal_id: None`
   (previous behavior exactly). replay/calibrate stay in `policy.py`.
3. 4-phase concept mapping (recorded, not migrated — coordinator already
   enforces these as per-slot oracles):
   - `landscape` → pre-dispatch reconnaissance obligations on the work item
   - `deep_dive`/`adversarial` → decision-slot depth + counterevidence
     requirements (`required_validation`, `counterevidence_required` on
     `DecisionSlotDeficit`)
   - `validation` → closure oracles blocking slot closure
4. Behavioral documents already teach generic "wave" vocabulary, not the dead
   module's API names — no vocabulary rewrite was needed beyond regeneration.

## Alternatives considered

- Keep `orchestration.py` with a deprecation shim — rejected: zero consumers.
- Retire `policy.py` too and migrate replay/calibrate into coordinator —
  rejected: the wiring branch passed TDD (no semantic mismatch found), so the
  smaller diff wins. Retirement remains the documented fallback if proposal
  semantics later diverge from dispatch inputs.

## Consequences

- `compile_orchestration_plan`, `validate_orchestration_plan`,
  `advance_execution`, `RESEARCH_PHASES`, `EXECUTION_STATES` leave the public
  API (`tests/test_scheduling_authority.py` locks this).
- Dispatch is the only scheduling entry point; policy is its advisory input.
- Rollback: revert this change; nothing else depends on the wiring.
