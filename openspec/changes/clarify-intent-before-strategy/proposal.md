## Why

An ambiguous requester brief can currently be converted into a technical strategy from a topic word such as `app`, even when the customer, payer, value proposition, or success decision is unknown. The resulting research may be internally coherent but solve the wrong problem. #87 makes the ambiguity a persistent, replayable Stage-1 object before strategy or autonomous work is allowed.

## What Changes

- Persist the literal requester wording and a versioned set of competing intent hypotheses with exact input lineage.
- Validate material ambiguity fields: requester ownership, researchability, decision consequence, evidence basis, disposition, and next action.
- Add a deterministic policy that selects bounded reconnaissance for researchable uncertainty and at most one bounded open question for material requester-exclusive choices.
- Add a versioned `DecisionFrame` with explicit `ready_for_strategy` or unresolved disposition and exact hypothesis lineage.
- Gate strategy projection, research-plan creation, and coordinator autonomous dispatch on a current ready DecisionFrame for the same run and target.
- Add replay, hostile intent-substitution, cross-host serialization, and fault-injection tests; topic words alone must never select technical scope.

## Capabilities

### New Capabilities

- `decision-frame`: Persistent, evidence-aware intent hypotheses, clarification policy, DecisionFrame readiness, and strategy-bound lineage.

### Modified Capabilities

<!-- No separately maintained base capability spec exists in this repository; lifecycle gating is specified as part of decision-frame. -->

## Impact

- New runtime models/validators and SQLite-backed artifact/event persistence in `src/research_tree/`.
- Coordinator strategy/dispatch guards and public exports.
- New schemas, fixtures, OpenSpec governance registry entries, and focused tests.
- Existing RunStore intent/brief readers remain compatible; canonical lifecycle paths gain a fail-closed readiness check.
