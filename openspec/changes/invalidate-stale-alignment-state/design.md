## Context

Group 7 already persists replayable alignment actions and enforces pending
response and human-only belief boundaries. Group 5 owns lifecycle authority in
`ResearchRunCoordinator`, while feedback rounds already demonstrate immutable
predecessor/successor artifacts in `RunStore`. The missing contract is a single
RunLedger transaction that turns a requester correction into a coordinator
control event and prevents old alignment/strategy/handoff state from remaining
executable.

## Goals / Non-Goals

**Goals:**

- Validate one strict correction/reopen value before storage mutation.
- Preserve exact predecessor artifacts and create explicit successor lineage.
- Quarantine exact affected revisions and digests in the coordinator ledger.
- Require current authority bindings for sensitive actions after correction.
- Keep task identity and domain identity independently addressable.
- Reuse existing pending-action and human-only alignment guarantees.

**Non-Goals:**

- Host UI or prompt behavior, provider changes, causal replay tooling,
  DecisionFrame design, four-stage strategy projection, or scheduler policy.
- Destructive migration or deletion of historical artifacts.
- A second lifecycle writer outside `ResearchRunCoordinator`.

## Decisions

### Use a frozen typed correction value at the feedback boundary

`feedback.py` will define the correction/reopen value and exact affected
bindings. Each binding combines an `ArtifactRef` with its content digest; the
five affected roles are explicit and validated. A single `task_id`/`domain_id`
pair plus successor pair prevents the diagnostic subject from being silently
substituted for the task. A permissive free-form mapping was rejected because
missing roles and identity conflation would only be discovered after mutation.

### Commit correction, quarantine, and successor state in one ledger batch

`ResearchRunCoordinator.apply_correction` will preflight every binding as a
current artifact of the expected kind, then append the correction event,
stale-state quarantine, and next `run-state` revision through
`append_artifact_batch`. The successor state returns to `alignment`, carries the
new identity pair and exact correction/quarantine refs, and links to the prior
state. Reusing `create_successor` was rejected because it creates a second run
before the old run's correction transaction has committed.

### Quarantine exact references instead of matching labels or prose

The quarantine payload stores role, exact artifact ref, content digest, and
relation. Guards compare caller-supplied bindings to both the quarantine and the
current ledger revision. This makes stale rejection deterministic and prevents
silent rebinding to an artifact with the same id. Global invalidation flags were
rejected because they cannot explain which revision became stale.

### Require authority bindings only after a correction epoch exists

Existing runs retain compatibility until a material correction is recorded.
Afterward, dispatch and sensitive lifecycle events must supply current alignment,
strategy, and handoff bindings plus the latest correction event id. The guard is
centralized in the coordinator so direct `complete` calls cannot bypass it.
Ordinary transition/evidence guards still run after authority validation.

### Keep alignment protocol protections at their current owner

`AlignmentProtocol.respond` remains the pending-question boundary and
`record_belief`/`readiness` remain the requester-only authority boundary. #73
adds regression assertions rather than duplicating these rules in correction
code.

## Risks / Trade-offs

- [Callers after correction must provide fresh bindings] -> Return the latest
  correction id and required roles in the machine-readable stale error so the
  caller can re-enter alignment and bind a successor.
- [A correction can arrive after delivery artifacts exist] -> Quarantine exact
  authority and reset lifecycle to alignment; historical delivery artifacts stay
  readable but cannot satisfy current completion.
- [Legacy runs lack a correction epoch] -> Apply strict post-correction guards
  only when a correction artifact exists; do not synthesize historical events.
- [Multiple artifact stores exist during migration] -> Limit this issue's
  transactional authority to RunLedger/coordinator state and retain existing
  feedback-round history behavior as a separately tested compatibility surface.

## Migration Plan

The schema change is additive at the artifact-kind level and needs no database
migration. Deploy typed correction parsing and coordinator guards together. On
rollback, stop accepting new corrections and keep correction/quarantine/state
artifacts readable; never reactivate quarantined bindings or rewrite history.

## Open Questions

None. The issue contract fixes the affected roles, coordinator ownership,
machine-readable stale reason, and rollback behavior.
