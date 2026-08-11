## Context

The existing `IntentModelCompiler` persists hypotheses and `QuestionPolicy`
can recommend one question, but the canonical SQLite coordinator does not have
a versioned artifact that proves the requester-owned decision surface is ready.
RunStore intent/brief artifacts remain useful compatibility inputs; the new
DecisionFrame must be immutable, replayable, and bound to exact input and
hypothesis revisions before it can authorize strategy or dispatch.

## Goals / Non-Goals

**Goals:**

- Add a strict, JSON-serializable DecisionFrame model and schema with bounded
  hypothesis fields, clarification decisions, and exact lineage.
- Persist frames through `RunLedger` with expected-revision atomicity and
  deterministic replay; expose a coordinator guard for strategy, plan, and
  autonomous dispatch.
- Keep topic words and fixed domain-to-method rules out of the decision.

**Non-Goals:**

- Replacing the existing RunStore intent compiler or implementing the later
  four-stage StrategyProjection (#85).
- Inferring business facts from keywords, automatically answering
  requester-exclusive choices, or adding a method/template rule base.

## Decisions

1. **Typed immutable artifact.** Add `DecisionFrame` and `IntentHypothesis`
   value objects in `decision_frame.py`, with strict enums, bounded strings,
   normalized tuples, `to_dict`/`from_dict`, and a content digest. The ledger
   stores the serialized artifact as `decision-frame` and exact parent refs.
   A plain mapping remains an input convenience but is validated before write.
   The canonical frame is authored from RunLedger-owned input/handoff refs.
   Existing RunStore `IntentModel` and `WorkingBrief` ids are accepted only
   through an explicit imported input artifact; they are never inserted as
   cross-store parent refs or treated as canonical authority.

2. **Explicit disposition instead of implicit confidence.** Every material
   hypothesis records `ambiguity`, `owner` (`requester`/`research`/`shared`),
   `researchable`, `decision_consequence`, `source_refs`, `disposition`, and
   `next_action`. A frame is `ready_for_strategy` only when every material
   unresolved choice is either evidence-ranked with a selected hypothesis or
   explicitly accepted by the requester; no keyword can satisfy this gate.
   Each frame also names one `primary_decision` and maps every enabler or
   constraint hypothesis to that decision. A no-progress reconnaissance result
   must either reframe the hypothesis or retain its explicit consequence and
   disposition; it cannot silently become a technical default.

3. **Bounded clarification policy.** `ClarificationPolicy` deterministically
   returns zero or one `OpenQuestion`. It selects only requester-owned,
   material, non-researchable unresolved alternatives; researchable ambiguity
   yields a `reconnaissance` action. Repeated evaluation of the same frame is
   byte-stable and does not create another prompt.

4. **Coordinator-owned gate.** `ResearchRunCoordinator.require_decision_frame`
   resolves the exact current frame, verifies its run/target lineage and ready
   status, and raises `CoordinatorConflictError` otherwise. The existing
   lifecycle transition and dispatch methods call the guard when a strategy,
   research plan, or autonomous action is supplied. The guard is read-only;
   frame persistence is a separate expected-revision ledger operation.

5. **Compatibility projection.** Existing RunStore readers may continue to
   consume legacy intent/brief artifacts. They cannot be treated as a ready
   DecisionFrame unless a new frame with matching parent refs is present in the
   canonical ledger.

6. **Migration contract.** Bump the executable ledger migration from version 3
   to version 4, create a `decision_frames` projection keyed by exact artifact
   ref, and backfill no legacy rows. A frame write and projection row commit in
   one transaction; migration rollback drops only the empty projection and
   leaves generic artifacts/events untouched. The checked-in Alpha2 SQLite DDL
   records the same table and migration digest.

## Risks / Trade-offs

- [Incomplete legacy lineage] -> legacy runs remain readable but are blocked
  from new strategy/dispatch gates until a frame is compiled.
- [Over-questioning] -> deterministic policy caps output at one question and
  prefers reconnaissance when evidence can resolve the ambiguity.
- [Concurrent frame writers] -> ledger expected revisions and idempotent event
  hashes fail closed on stale or conflicting retries.
- [Cross-host drift] -> canonical JSON and schema fixtures are shared by all
  host adapters; host-specific prompts are observations, not authority.
- [Technical substitution at delivery] -> every technical/enabler reference
  carries the primary-decision ref and delivery validation rejects a package
  whose stack claim lacks that trace.

## Migration Plan

1. Add schema/validator, red tests, ledger persistence, and coordinator guard.
2. Keep existing intent/brief projections readable and route new canonical
   strategy/dispatch callers through `require_decision_frame`.
3. Roll back by disabling the new gate for legacy read-only projections while
   retaining immutable frame artifacts; never delete ledger history.

## Open Questions

- #85 will define the later StrategyProjection digest; this change binds only
  the prerequisite DecisionFrame and leaves the downstream projection schema
  unchanged.
