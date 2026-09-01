## Context

Alignment actions are replayable and human-only beliefs are protected, but a requester correction did not invalidate executable strategy/handoff state. The coordinator must own one append-only correction transaction and all later authority checks.

## Goals / Non-Goals

**Goals:** strict correction values; immutable supersession; lineage-bound quarantine; exact current authority; independent task/domain ids; existing pending-action and human-only guarantees.

**Non-Goals:** UI/provider behavior, causal replay, strategy redesign, scheduler policy, destructive migration, or another lifecycle writer.

## Decisions

### Frozen correction value

`feedback.py` defines correction/reopen plus five exact role bindings. Separate source and successor task/domain pairs prevent a diagnostic subject from silently replacing the task. Missing roles fail before mutation.

### One ledger transaction

`apply_correction` preflights identity and bindings, then appends correction, quarantine, and successor `run-state` in one batch. The successor returns to alignment and links the immutable predecessor through `supersedes`/`reopens`.

### State-owned authority streams

When the complete chain exists, initialization records its unique target-to-intent artifact ids and task/domain identity. Correction input must equal the exact current revisions in those streams; being latest for a parallel id is insufficient. Post-correction actions likewise must equal the canonical current decision-map/strategy/handoff set, so the first caller cannot nominate parallel children.

### Lineage quarantine

The quarantine stores exact stale bindings and only latest dependent artifacts reachable from affected refs or predecessor state. Kind-wide invalidation was rejected because it captures unrelated work. Central guards cover dispatch, confirmation, delivery, acceptance, and direct completion.

### Existing alignment authority remains local

`AlignmentProtocol.respond` retains pending-action ownership and `record_belief`/`readiness` retain requester-only authority; correction tests exercise those rules without duplicating them.

## Risks / Migration

- Callers after correction must rebuild recorded streams and pass exact bindings; stale errors return the correction id and re-entry action.
- Historical delivery stays readable but cannot satisfy current completion; legacy runs without a complete chain keep pre-correction behavior.
- The additive artifact kinds need no database migration. Rollback stops new corrections but never rewrites history or reactivates quarantined refs.
