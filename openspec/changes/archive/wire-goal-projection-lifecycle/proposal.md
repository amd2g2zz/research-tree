# Wire Goal Projection Lifecycle

## Why

The confirmed StrategyProjection — the user-confirmed primary goal — is unreachable in real
runs: `display_strategy`/`confirm_handoff` had zero production callers and
`initialize_research_from_alignment` was never invoked on the production path, so slot-level
goal wiring could never reference a confirmed projection. Issue #427 wires the projection
lifecycle into the production path first, then lands slot `serves` validation on top of it.

## What Changes

- Add a `strategy` command group to the stable CLI: `strategy propose --projection <json>`,
  `strategy display`, and `strategy confirm --confirmation <text>`.
- `strategy display` performs the runtime-side falsifiability review before advancing the
  run: every success oracle must carry non-empty `evidence_standard_ids`, and decision-target
  oracle references must resolve inside `success_oracles`.
- `strategy display` commits the displayed projection revision (draft → displayed) and drives
  the `alignment_projection_ready` transition with the coordinator's existing digest guard.
- `strategy confirm` keeps the authoritative `actor="human"` semantics and the digest-in-
  confirmation check, pre-flights that the alignment graph is confirmed, and bridges to
  `initialize_research_from_alignment` so confirmation produces the research tree.
- Decision Slot payload gains the required `serves: {target_id, oracle_ids}` link (slot
  whitelist in `decision_map.py`); `CanonicalWorkItemCompiler` validates it against the run's
  current confirmed (and falsifiability-checked) projection, rejecting the whole work item
  otherwise.
- Confirmation is recorded by the run's `handoff_confirmed` lifecycle event; the confirmed
  projection basis is the projection revision that event names (digest-matched), queried via
  `strategy_projection.latest_confirmed`.
- Alignment-handoff payload assembly records `confirmed: true` and the `goal_decomposition`
  (`[{slot_id, target_id, oracle_ids, priority}]`, priority→slot_id ordering) derived from
  Decision Slots' serves links.
- Strategy display output includes the goal→slot decomposition mapping.

## Capabilities

### New Capability: goal-wiring

### Modified Capabilities

(none)

## Impact

- `src/research_tree/work_items.py` — slot serves validation at compile.
- `src/research_tree/strategy_projection.py` — confirmed-projection query + falsifiability
  review rules.
- `src/research_tree/decision_map.py` — slot whitelist gains required serves shape.
- `src/research_tree/alignment_handoff.py` — handoff payload: confirmed flag + goal
  decomposition.
- `src/research_tree/coordinator.py` — the `alignment_projection_ready` transition guard
  enforces the falsifiability review for every caller (display_strategy included); the
  display method and the CLI display verb pre-flight the same rules for message fidelity
  and zero-mutation rejections, confirm re-validates the projection content, and confirm
  keeps `actor="human"` with the digest guard.
- tests: new `tests/test_goal_wiring.py` contract tests; existing fixtures gain serves and a
  confirmed-projection setup.
