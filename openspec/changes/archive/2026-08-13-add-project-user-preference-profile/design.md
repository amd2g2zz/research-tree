## Context

Issue #85 introduced immutable StrategyProjection artifacts and a SQLite read model, but the runtime has no bounded mechanism for durable requester preferences. Raw transcripts and hidden profiling are prohibited. The new capability must keep explicit current input authoritative, survive process reload, expose every retained value, and remain removable without rewriting unrelated run history.

## Goals / Non-Goals

**Goals:**

- Define content-bound observation and profile values with strict privacy fields.
- Persist project-local observations and profile revisions in the workspace ledger.
- Refresh inferred evidence once per five observed turns with one-step hysteresis.
- Represent contradiction, aging, supersession, and reversal without silently changing active behavior.
- Expose deterministic inspect, correct, reset, and delete operations.
- Attach bounded preference lineage to each materially influenced StrategyProjection.

**Non-Goals:**

- Global or cross-project identity, demographic or psychological inference, transcript retention, model confidence claims, or automatic override of the current explicit request.
- A second strategy authority or mutation of already persisted StrategyProjection revisions.
- Natural-language preference extraction; callers provide bounded observation keys and normalized values.

## Decisions

### Bounded domain records rather than transcript-derived state

`PreferenceObservation` stores a project id, stable observation id, turn number, normalized preference key/value, explicit or inferred basis, source reference, privacy classification, reversal condition, supersession reference, and digest. Free-form transcript, prompt, demographic, and secret fields are rejected. `UserPreferenceProfile` stores only inspectable entries plus pending observation ids and revision lineage.

Alternative: retain conversation excerpts and periodically summarize them. Rejected because it makes deletion ambiguous, increases privacy exposure, and creates an unauditable inference surface.

### Five-turn refresh with a one-step state machine

The service records every valid observation immediately but refreshes inferred evidence only when `turn_number` reaches the next five-turn boundary. Each entry moves at most one step per refresh: `candidate` to `active`; active contradiction to `contested`; unresolved contested values remain active while an alternative is stored as `shadow`; aged entries become `stale`. A single inferred observation cannot reverse an active value. Explicit observations apply immediately and supersede the prior active value with exact previous/next lineage.

Alternative: continuously update confidence scores. Rejected because floating scores are hard to inspect, are volatile under one-off input, and obscure the actual transition that changed behavior.

### Project-local SQLite authority and reconstructable read model

The workspace ledger receives append-only `preference_observations` and revisioned `user_preference_profiles` tables. The service reads the latest profile and pending observations after reload. Reset appends an empty profile revision while retaining immutable observations read-only; delete removes this project's preference rows only, satisfying project-record deletion without touching run artifacts.

Alternative: store a JSON file next to each run. Rejected because preferences span runs within one project and would lack transactional reload and deletion behavior.

### Explicit administration boundary

The public service offers `inspect`, `observe`, `correct`, `reset`, and `delete`. Correction is an explicit observation and therefore has immediate precedence. Inspection returns normalized records only. Reset and delete require the exact project id; there is no implicit global current user.

### Strategy influence is optional, structured, and content-bound

`StrategyProjection` gains an optional tuple of preference influences. Every influence names the profile revision, observation id, key, selected value, precedence (`current-explicit` or `profile`), and reversal condition. Projection hashing includes the tuple. Old serialized projections without the field remain readable as an empty tuple, while new writes emit it. Callers must omit profile influence when a current explicit request conflicts.

Alternative: mutate strategy fields silently from a service-level profile. Rejected because it cannot prove why a projection changed or whether current input won.

## Risks / Trade-offs

- [Five-turn batching delays useful inference] -> Explicit corrections remain immediate; inferred values deliberately trade latency for stability.
- [Deletion removes audit data] -> Deletion is explicit and project-scoped; reset is the default reversible control and retains observations read-only.
- [Optional projection field changes digest shape] -> New writes include the field; compatibility reads normalize legacy projections before validation.
- [Callers invent sensitive keys] -> Domain validation rejects blocked privacy classes and sensitive/psychological/demographic key namespaces.

## Migration Plan

1. Add schema version 6 tables and JSON schemas without backfilling a profile.
2. Introduce the domain/service APIs and deterministic reload tests.
3. Add optional StrategyProjection influence lineage and legacy-read compatibility.
4. Roll back by disabling profile influence and administration writes while retaining observation history read-only; current explicit input and existing projections remain authoritative.

## Open Questions

None. The issue contract fixes five-turn refresh, explicit precedence, project scope, and privacy boundaries.
