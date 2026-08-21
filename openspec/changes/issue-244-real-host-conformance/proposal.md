## Why

#241 (Codex) and #242 (Hermes) closed with real live receipts and #243
(Claude) is closed on dev, but no gate yet proves the three hosts produce
equivalent canonical research semantics through real host processes. The
prior cross-host tests submitted capability strings and synthetic
dictionaries; the closed #82 reported completion without live acceptance.

## What Changes

- One small deterministic logical research task
  (`evaluation/cases/host-conformance-v1.json`): two independent leaves, one
  contradiction, one validation phase, expected canonical events, negative
  oracles for projected/synthetic completion.
- Claimed modes with per-mode evidence requirements: Codex collaboration
  (app-server spawnAgent surface), Claude Agent, Claude Workflow, Claude
  hybrid, Hermes `delegate_task` (synchronous delegation channel).
  Unavailable modes record blockers, never passes.
- `evaluation/harness/host_conformance.py` + `run_host_conformance.py`:
  run each claimed mode from fresh project roots with real host processes;
  normalize canonical semantics only (project/run/task/attempt identity,
  event kinds, revision/sequence, Finding Pack admission, contradiction
  replanning, checkpoint recovery, completion gating); require source-bound
  digests and true child identities.
- Fault injection: provider interruption, cancellation, hook loss, process
  kill, stale child, missing/modified artifact, resume, fork. Assert
  `unknown`/`failed`/blocked/retry/recovery exactly; no false completion.
- Replay: persisted project artifacts only, separate process; compare
  accepted canonical state, unresolved work, attempt IDs, causal sequence.
- Comparison table: every prior synthetic/pilot attempt, its non-acceptance
  reason, and the new source-bound receipt that supersedes it.
- Docker envelope per mode cell where the host permits; explicit reviewed
  deviations otherwise (as accepted for the Codex app-server surface in #241).

## Non-Goals

- No runtime fixes in this lane: failures return to the owning (closed) lane
  as follow-ups; #244 is verification-only.
- No mocked host events, no synthetic receipts, no pooled pilot results.

## Non-Acceptance Conditions

- A mode marked available without a real normal+fault receipt pair.
- Replay divergence between persisted artifacts and fresh-process state.
- `unavailable` recorded as a pass; capability probes as completion evidence.
