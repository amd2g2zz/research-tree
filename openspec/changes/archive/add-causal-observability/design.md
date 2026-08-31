## Context

`ResearchRunCoordinator` atomically appends a lifecycle-event and a new research-run-state, while `RunLedger` retains immutable artifacts and parent references. The older `.research-tree-debug` JSON files are intentionally optional and non-authoritative. The missing layer is a deterministic, sanitized projection that can prove state lineage and explain decisions without introducing another store.

## Goals / Non-Goals

**Goals:**

- Reconstruct and verify canonical lifecycle state solely from immutable ledger artifacts.
- Expose stable explanations for runs, actions, completion blockers, and host discrepancies.
- Reject ambiguous lineage and sensitive or unbounded diagnostic input.
- Preserve machine-readable ordering and exact evidence references.

**Non-Goals:**

- Traces do not mutate lifecycle state or become a completion authority.
- This change does not persist prompts, raw provider failures, or private reasoning.
- This change does not redesign adaptive policy or implement correction invalidation.

## Decisions

1. Add a `CausalTraceService` beside the existing debug CLI. It reads `RunLedger` snapshots and projects lifecycle-event plus research-run-state pairs; no trace table or side database is added. This uses the canonical immutable artifacts and keeps rollback trivial.
2. Replay follows lifecycle revisions, not timestamps. Every state after initialization must reference its exact previous state and one lifecycle event whose `from`, `to`, and event identity agree. Recorded state digests are recomputed from payloads and compared before a terminal digest is returned.
3. A stable trace record exposes bounded fields: schema, trace/event/run IDs, sequence, actor, host, action, cause/correlation IDs, prior/next digests, inputs, score components, outcome, reason, redaction class, retention class, and artifact refs. Missing optional data becomes an empty bounded value; arbitrary provider payload is never copied.
4. `why_not_complete` retains its compatibility keys and adds evidence gaps derived from current ledger artifacts. `reconcile_host` accepts a bounded observation schema and only classifies discrepancies against canonical attempt/host-event artifacts.
5. Extend `research-tree-debug` with ledger-backed subcommands. JSON input is parsed as structured data and validated; output ordering and digesting are deterministic.
6. A TDD slice is green only when focused pytest, Ruff lint, and Ruff formatting checks all pass. The same combined command is recorded in group-11 verification evidence.

## Risks / Trade-offs

- [Legacy states may lack complete causal links] -> Replay reports unresolved references and fails verification rather than inventing lineage.
- [Artifact payloads can contain sensitive data] -> Projection uses an allowlist of scalar identifiers/categories and rejects sensitive keys before export.
- [Host snapshots can be stale or adversarial] -> Reconciliation is bounded, read-only, and never changes coordinator state.
- [Compatibility callers rely on current why-not-complete fields] -> Existing fields remain unchanged; evidence-gap details are additive.

## Migration Plan

Ship projection APIs and CLI commands without migrating data. Existing canonical runs are replayable when their lifecycle lineage is complete; older local debug files remain readable through `summary`. Rollback removes the new projection commands and leaves all ledger artifacts untouched.

## Open Questions

None for this issue; correction-event invalidation remains owned by #73.
