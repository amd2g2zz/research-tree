# Proposal: normalize-host-attempt-outcomes

## Why

issue #326 (confirmed): Hermes Docker runs returned process exit 0 while the
model operation failed with HTTP 401/429. Exit codes are not truth; the
stable lifecycle lacks a mandatory normalization boundary converting process/
provider/usage/deliverable/lifecycle signals into one typed attempt result
before coordinator ingestion.

## What Changes

1. `src/research_tree/host_attempts.py`: `HostAttemptOutcome` (process exit,
   timeout, provider/usage disposition, expected+observed deliverables, host/
   session/attempt identity, canonical event refs); `classify_attempt` with
   documented precedence (timeout>auth>unavailable>incompatible>deliverables);
   seven mutually exclusive dispositions; `worker_finished_eligible` gate.
2. Coordinator guard: `worker_finished` events carrying `attempt_outcome`
   with a semantic failure raise `attempt_outcome_semantic_failure` /
   `attempt_outcome_invalid`. No key → previous behavior exactly.
3. `doctor` output splits static installation health from live provider
   readiness (probe-declared `unknown` when not probed; no credentials/logs).
4. `evaluation/cases/host-attempt-normalization-v1.json`: replayed fixtures
   (exit-0 semantic failure ×3, non-zero, timeout, partial, success ×3 hosts).
5. tests/test_host_attempt_normalization.py: 13 tests, one per acceptance
   line + mutual exclusivity + coordinator guards + doctor separation.

## Impact

- src: host_attempts.py (new), coordinator.py (guard only), cli.py (doctor section)
- evaluation: one fixture file (registered per check_evaluation_assets rules)
- Timeout→unknown_outcome precedes any retry by classification order.
