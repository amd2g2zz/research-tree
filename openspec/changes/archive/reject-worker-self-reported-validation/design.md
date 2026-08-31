## Context

`apply_research_results()` ingests legacy Finding Packs and calls
`_grow_from_finding()` for each fresh result. That function currently maps a
worker-owned `validation_result.status` directly to the authoritative
`DecisionSlot.validation_passed` state. `evaluate_research_stop()` then uses
that state to close the slot and permit delivery.

The Alpha2 contract reserves closure for evaluator-owned executable OracleRun
evidence. The full OracleRun migration is separately tracked under #56. This
change protects the live legacy projection now, without claiming to implement
that canonical runtime.

## Goals / Non-Goals

**Goals:**

- Prevent worker observations from changing authoritative validation truth.
- Preserve a worker-reported pass as useful, explicitly untrusted information.
- Require a deterministic, mandatory continuation for independent proof.
- Retain existing failure counting and retry behavior.
- Keep duplicate worker reports idempotent.

**Non-Goals:**

- Define or persist OracleRun records, evaluator identities, or canonical
  slot-closure artifacts.
- Change delivery, readiness, host packaging, schemas, or storage.
- Reclassify this compatibility guard as completion of Alpha2 task 4.3.

## Decisions

### Do not mutate `validation_passed` during worker ingestion

The Finding Pack boundary SHALL leave the existing authoritative
`validation_passed` value untouched. New slots begin with `False`, so a worker
pass cannot close them. Leaving an existing value untouched is safer than
writing `False`: later evaluator-owned code can set a real pass without a
subsequent worker report erasing it.

Alternative considered: always assign `False` for every worker validation
result. Rejected because it turns a non-authoritative observation into an
authoritative invalidation and would corrupt future evaluator-owned state.

### Represent a worker pass as an untrusted observation and one active validation node

For `status == "passed"`, store
`validation_status="reported_passed_untrusted"`, increment the existing
attempt count, and add a mandatory verifier-needed validation node. The node
requests an evaluator-owned or otherwise independent OracleRun; it does not
claim that such proof has occurred. It is created directly in the worker-pass
path rather than through `_ensure_slot_frontier()`, because unrelated frontier
work must not suppress this obligation.

The slot keeps a local continuation epoch. Fresh passes reuse the same epoch
while its verifier-needed node is still in the frontier, so they produce one
active continuation. If that node has completed while the slot remains
unvalidated, the next fresh pass advances the epoch and creates a new active
continuation. This avoids a historical node identity permanently suppressing
future recovery work. The verifier node uses a protocol-owned identity
namespace, separate from the worker question namespace, so a worker cannot
pre-create a look-alike continuation that captures the verifier node's identity
or pruning equivalence. A `frontier` or `running` verifier node is active; only
a terminal node permits a new epoch.

Alternative considered: discard the reported pass. Rejected because the agent
still needs to know why an independent check was requested and operators need
an auditable observation.

### Preserve recognized non-pass compatibility and reject malformed mappings

`failed` continues to record `validation_status`, increment attempts and
failure count, then lets `_ensure_slot_frontier()` create its existing
independent-method retry. A recognized `inconclusive` result continues to
record an attempt and use the existing continuation path. Missing, non-mapping,
or mapping values whose `status` is absent, non-string, empty, or outside the
three recognized statuses (`passed`, `failed`, `inconclusive`) are malformed
observations and are ignored without changing slot state or attempt counters.

### Do not retroactively certify legacy persisted passes

Existing recursive-search snapshots carry only `validation_passed`, without an
authority or OracleRun provenance field. This slice does not infer whether a
historical `true` value came from a worker or evaluator, and therefore does not
retroactively certify it. It prevents new worker ingestion from creating or
overwriting authoritative state; #56 remains responsible for canonical
provenance, migration, and quarantine rules.

## Risks / Trade-offs

- [Legacy states lack an evaluator write path] -> Newly unvalidated slots stay
  open; #56 remains responsible for canonical OracleRun closure.
- [Historical `validation_passed=true` has no provenance] -> Do not claim this
  slice repairs it; record it as a #56 migration/quarantine follow-up.
- [Repeated reports can inflate attempt metrics] -> Keep the current per-fresh
  Finding Pack accounting but make the required continuation deterministic and
  idempotent.
- [A narrow fix could be mistaken for Alpha2 completion] -> State the explicit
  non-goal in OpenSpec, the issue tracker, and the verification receipt.

## Migration Plan

No migration is required. Existing persisted states retain their current
authoritative value; newly ingested worker results no longer overwrite it.
Rollback is a code revert. No stored schema or generated package changes.

## Open Questions

None for this compatibility boundary. The authority and persistence model for
an evaluator-owned pass belongs to the canonical OracleRun work.
