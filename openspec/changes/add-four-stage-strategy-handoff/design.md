## Context

The coordinator already owns detailed lifecycle transitions and exact-revision event ingestion, while alignment stores digest-bound messages and DecisionFrame readiness. The missing boundary is a complete strategy artifact between intent readiness and autonomous dispatch. The design must preserve existing lifecycle and correction behavior, support SQLite replay, and expose equivalent semantics through three thin host adapters.

## Goals / Non-Goals

**Goals:**

- Persist one canonical, immutable StrategyProjection with deterministic content digest and revision lineage.
- Require proof that the current projection was displayed and explicitly confirmed before dispatch.
- Project detailed lifecycle states into four monotonic requester-visible macro stages.
- Keep strategy-only revisions in the same run and route material target-basis changes through successor creation.
- Preserve exact semantic parity across Codex, Claude Code, and Hermes transports.

**Non-Goals:**

- Preference rollups, search portfolio generation, native dynamic workflows, dual-delivery semantics, or candidate evaluation.
- A host-specific workflow state machine or a second completion authority.
- Treating projection display or confirmation as delivery acceptance.

## Decisions

### Canonical immutable projection

`StrategyProjection` is a frozen domain value. Its digest is SHA-256 over canonical JSON excluding the digest field. Required tuple fields reject empty values; mappings are normalized before hashing. This follows existing content-bound artifact patterns and makes replay platform-independent.

Alternative: reuse an alignment strategy string. Rejected because it cannot prove field completeness, exact display, or stable cross-host semantics.

### Four-stage projection over existing lifecycle

The detailed lifecycle remains authoritative. A pure `macro_stage_for_state` mapping exposes stage 1 alignment, stage 2 strategy review, stage 3 research/readiness, and stage 4 delivery/acceptance. Pause and block records retain the previous macro stage so resume cannot regress or jump stages.

Alternative: replace lifecycle states with four states. Rejected because it would erase recovery, synthesis, readiness, and acceptance distinctions.

### Coordinator-owned transactional handoff

The coordinator persists projection revisions and display receipts. Confirmation must name the current projection id, revision, digest, display receipt, and contextual acceptance. Incomplete, stale, undisplayed, generic, duplicate-conflicting, or correction-invalidated confirmations fail before state mutation. Dispatch checks the confirmed current digest.

Alternative: let alignment or adapters transition directly. Rejected because that creates split authority and weakens correction invalidation.

### Revision versus successor classification

Method, track, evidence, depth, replanning, delivery detail, or stop-rule changes append a same-run projection revision and invalidate prior display/confirmation. Outcome, target, scope, authority, safety, or success-oracle changes supersede the run and return the successor to stage 1.

### Host semantic envelope

Adapters serialize the same canonical projection payload and digest with host metadata outside the semantic payload. Missing native capability is an explicit unavailable disposition, never a semantic pass.

## Risks / Trade-offs

- [Large projection payloads increase event size] -> Store one canonical artifact and reference it by id/revision/digest from events.
- [Legacy runs lack projections] -> Keep them read-only and require a new projection before any new stage-3 dispatch.
- [Pause state loses its origin] -> Persist prior macro stage in transition payload and reconstruct it during replay.
- [Digest drift across hosts] -> Canonical JSON, normalized collections, and parity fixtures bind all hosts to one digest.

## Migration Plan

1. Add the projection schema and SQLite table/indexes without backfilling authority.
2. Add coordinator APIs and dispatch guards; legacy runs remain readable but cannot newly dispatch without projection confirmation.
3. Update lifecycle/host registries and package sources, then rebuild generated packages.
4. Roll back by disabling new confirmation entry points while retaining immutable projection and event history.

## Open Questions

None. Issue #85 and the merged DecisionFrame/correction contracts define the material-change boundary.
