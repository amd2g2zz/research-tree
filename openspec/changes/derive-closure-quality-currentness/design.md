## Context

Issue #160 makes the exact direct Finding set and each Finding's durable
evidence chain available to `SlotClosureAssessor`. The assessor still receives
provenance groups, a counterevidence disposition, and an active contradiction
from its caller. It persists those claims rather than replaying a typed result
against the current graph.

Issue #161 is the second child of parent #152. It consumes #160's strict graph
without changing content binding, generic writer admission, completion
registration, correction propagation, or the parent group-39 receipt.

## Goals / Non-Goals

**Goals:**

- Derive usable `(method_id, provider_id)` boundaries through a strict
  Finding-to-evidence-to-receipt-to-capture chain.
- Require an exact current passed candidate OracleRun to witness a
  contradiction Finding for the decision's selected option.
- Persist a replayable version-two assessment envelope and provide an
  `is_current()` API that replays it against exact current graph inputs.
- Fail closed for malformed, incomplete, stale, and tampered assessments.

**Non-Goals:**

- Inferring worker or reviewer identity, proving a completed counterevidence
  search, discovering omitted or failed OracleRuns globally, or creating a
  general semantic-adjudication system.
- Changing #160 CAS/content/strict-anchor admission or adding persistence
  formats for capture, evidence, receipt, or Finding artifacts.
- Rejecting generic ledger writes at the canonical completion-registration
  boundary (#156), consuming the final completion manifold (#158), propagating
  corrections (#153), changing coordinator completion, or adding CLI commands.

## Decisions

1. **Derive only properties the graph can prove.** Independence requires two
   distinct usable `(method_id, provider_id)` boundaries resolved from canonical
   capture lineage. A contradiction is only a direct decision Finding whose
   effect contradicts the selected option. It remains unresolved unless an
   exact current passed OracleRun includes that Finding reference in its
   `input_refs`. There is no claim that an OracleRun adjudicates every possible
   contradiction or that an omitted run can be detected.

2. **Ignore caller quality arguments completely.** `assess()` retains
   `provenance_groups`, `counterevidence_disposition`, and
   `active_contradiction` for source compatibility, but none may affect derived
   checks, successors, persisted payload fields, or the token. This makes the
   same canonical graph idempotent regardless of caller-supplied claims.

3. **Version the replay envelope.** Version-two assessments persist evaluator
   identity, exact parent references, derived checks and diagnostics, successor
   obligations, assessor version, and a deterministic token digest. Version-one
   artifacts remain history and fail currentness under the version-two replay
   contract.

4. **Replay exact state fail-closed.** `is_current()` reparses the stored
   version-two assessment; resolves the exact Finding/evidence/receipt/capture/
   origin and OracleRun/spec/attempt/input/result/event lineage; proves all
   inputs remain current and in the assessment run; recomputes derived checks;
   and compares the complete stored envelope and token. Missing, stale,
   malformed, or altered data returns false.

5. **Leave writer authority to its owners.** Data-only replay can reject raw
   incomplete or non-replayable artifacts. It cannot distinguish a
   byte-identical generic append from a canonical writer. #156 owns canonical
   registration and #158 owns final completion consumption.

## Risks / Trade-offs

- **Existing fixtures use caller claims.** Retain the call shape and update
  only focused fixtures to prove the arguments cannot influence results.
- **No formal adjudication artifact exists.** Treat an unwitnessed selected
  option contradiction as unresolved and emit adversarial follow-up work.
- **Replay could duplicate assessment logic.** Centralize snapshot and token
  construction so issue and replay share derivation.
- **Historical assessments cannot replay.** Retain them as immutable history
  and fail them closed under the new API.

## Migration Plan

No historical artifact is rewritten. Add a version-two schema while retaining
the version-one schema as historical documentation. Rollback treats
unprovable or stale version-two closures as inconclusive and retains all
immutable lineage.

## Open Questions

None. The child scope and group ownership are fixed by issue #161; parent #152
remains unverified until both child receipts are reachable.
