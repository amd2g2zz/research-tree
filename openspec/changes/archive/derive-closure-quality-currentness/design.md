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
- Persist the current version-two assessment envelope and provide an
  `is_current()` API that replays it against exact current graph inputs. The
  prior envelope is unsupported and has no compatibility reader or migration.
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

2. **Remove caller quality arguments completely.** `assess()` accepts only
   exact graph inputs. `provenance_groups`, `counterevidence_disposition`, and
   `active_contradiction` are not accepted, persisted, migrated, or replayed.
   This makes the same canonical graph idempotent without a compatibility
   shim.

3. **Replace the replay envelope.** Version-two assessments are the only
   supported payload. They persist evaluator identity, exact parent references,
   derived checks and diagnostics, successor obligations, assessor version, and
   a deterministic token digest. Version-one artifacts have no parser, schema,
   migration, or replay path.

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

- **Callers must use exact graph inputs.** The removed quality keywords fail at
  the API boundary; focused fixtures prove no compatibility shim remains.
- **No formal adjudication artifact exists.** Treat an unwitnessed selected
  option contradiction as unresolved and emit adversarial follow-up work.
- **Replay could duplicate assessment logic.** Centralize snapshot and token
  construction so issue and replay share derivation.
- **Prior assessments cannot replay.** They are unsupported and fail closed;
  Git history is the only retained record.

## Migration Plan

Replace the version-one schema and example with the version-two contract. No
legacy payload is migrated, replayed, or retained as an active artifact.
Rollback treats unprovable or stale version-two closures as inconclusive.

## Open Questions

None. The child scope and group ownership are fixed by issue #161; parent #152
remains unverified until both child receipts are reachable.
