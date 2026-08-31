# Require Goal Satisfaction Completion

## Why

`_completion_manifold` gates completion on p0 closure tokens, insight, readiness, evaluation,
and delivery acceptance — but never on the confirmed StrategyProjection's success oracles. A
run can reach `awaiting_acceptance` with every delivery surface green while the primary goal's
stated success signals carry no evidence mapping, so "wrong completion" is undetectable at the
gate. Issue #429 adds the `goal_satisfaction` diagnostic: completion is now gated on
per-oracle evidence-bound verdicts, fail-closed for runs whose confirmation record does not
resolve to a confirmed projection.

## What Changes

- Add completion-input role `goal_satisfaction` (kind `goal-satisfaction`, issuer
  `coordinator`) written by `CompletionInputRegistrar.write_goal_satisfaction`: one
  registration per success oracle, payload `{schema:1, oracle_id, verdict ∈ {satisfied,
  partial, unmet, waived}, evidence_refs: [<ArtifactRef>], waiver_reason}`. Payload
  validation is field-naming: verdict whitelist; `waived` requires a non-empty
  `waiver_reason`; `satisfied/partial/unmet` require `waiver_reason: null`;
  `satisfied/partial` require non-empty `evidence_refs`, and those refs are bound to the
  registration's exact parent lineage (satisfied/partial can never cite evidence the ledger
  does not hold). `unmet` evidence_refs may be empty.
- A `satisfied`/`partial` verdict counts only when at least one `evidence_ref` resolves to a
  current (latest-revision, non-quarantined) run artifact of an admissible evidence kind
  (`finding-pack`, `slot-closure-assessment`, `goal-contribution-assessment`). The PRD also
  lists "experiment result"; no such artifact kind exists in the runtime, so the set covers
  the three existing evidence classes. Registration parent lineage is validated by the
  registrar/ledger at write time (in-run, latest, non-quarantined) and re-derived by the
  manifold at diagnosis time, so later staleness re-opens the gate.
- Add the `goal_satisfaction` diagnostic to `_completion_manifold`. Fail-closed semantics:
  no resolvable confirmed projection (`strategy_projection.latest_confirmed`) → fail
  `goal_satisfaction_unknown` (never silently passes); any projection oracle without exactly
  one registration, or whose verdict is `unmet`, or whose evidence no longer resolves → fail
  `oracle_uncovered` with the uncovered oracle ids; more than one valid registration for the
  same oracle → fail `oracle_duplicate` with the duplicated oracle ids. On pass, the
  completion record's manifold records `goal_satisfaction_refs` (registration refs in
  projection oracle order).
- `complete()` blocks on the diagnostic fail with `CompletionBlockedError` (existing
  obligations path — zero new control flow). `why_not_complete` keeps its existing output
  shape and, for an `oracle_uncovered` fail, appends `resolve:goal_satisfaction:<oracle_id>`
  per uncovered oracle to `next_actions` alongside the generic `resolve:goal_satisfaction`
  obligation entry.
- Existing canonical completion fixtures register a waived goal_satisfaction input (with
  reason) where they previously completed without any goal gate; the fail-closed behavior is
  the specified contract change and the completion record manifold key set gains
  `goal_satisfaction_refs`.

## Capabilities

### New Capability: goal-wiring

### Modified Capabilities

(none)

## Impact

- `src/research_tree/run_ledger.py` — completion-input role whitelist gains
  `goal_satisfaction` → `goal-satisfaction` (pure addition; the seven existing roles and
  kinds are unchanged).
- `src/research_tree/completion_inputs.py` — `GOAL_SATISFACTION_*` constants,
  `validate_goal_satisfaction_payload` validator, and
  `CompletionInputRegistrar.write_goal_satisfaction`.
- `src/research_tree/coordinator.py` — `_goal_satisfaction_diagnostic` wired into
  `_completion_manifold`; `why_not_complete` appends per-oracle resolve entries.
- `tests/test_goal_gate.py` — new named contract tests; `tests/test_completion_manifold.py`
  and `tests/test_research_run_coordinator.py` fixtures updated for the fail-closed gate.
