# Tasks: divergence-aware-alignment-state

## 1. SDD

- [x] 1.1 Proposal, design (`impact_scope` + `rejected_designs`), capability
  spec delta from issue #496 scenarios.
- [x] 1.2 GitNexus index rebuild + upstream impact per symbol; CRITICAL on
  `_materialize` flagged with containment decision.

## 2. Divergence-axis state model (RED first)

- [x] 2.1 RED: `record(..., new_axes=...)` opens an axis — visible in
  `status()["divergence"]["axes"]` with `axis_id`, `node_id`, `description`,
  `status="open"`, `opened_turn`, `stagnant_turns=0`; the recorded node's
  stagnation resets; `next_action` is `plan` (not `reconnaissance`) and
  `dialogue_mode` is `divergent`.
- [x] 2.2 RED: axis state survives a persistence round-trip — reopening the
  store and `rebuild_materialized()` both restore axes and node stagnation
  byte-identically.
- [x] 2.3 RED: re-declaring the same direction dedupes to the same
  `axis_id`; an explicit id belonging to another node is rejected; unknown
  declaration fields are rejected.
- [x] 2.4 RED: a quiet turn stagnates the node and its open axes;
  `answered` converges the node's open axes; `reopened` re-opens them.

## 3. Divergence-aware plan decision (RED first)

- [x] 3.1 RED: a user answer that opens a new divergence axis keeps the
  controller in dialogue — `plan()` returns an exploratory `ask_one` naming
  `axis_id`, even with the node's ask budget spent.
- [x] 3.2 RED: stagnation localized in one node does not terminate
  exploration of another node — after one node stalls, `plan()` asks the
  next explorable node (never reconnaissance while an explorable node or
  active axis exists).
- [x] 3.3 RED: a genuine stall (no active axis, every requester-only node
  stalled) moves to reconnaissance with a stall reason — and a new axis
  declaration re-opens the dialogue.

## 4. Implementation (GREEN)

- [x] 4.1 `SCHEMA` 3, `divergence_axes` table, `nodes.stagnant_turns`,
  materialize/restore/rebuild of `state["divergence"]`.
- [x] 4.2 `record()` axis API + per-node stagnation + `dialogue_mode`/
  `opened_axes`/`next_action` semantics; module-level and CLI surface.
- [x] 4.3 `plan()` divergence-aware decision; global stagnation escape
  removed; `MAX_TURNS`/readiness branches untouched.
- [x] 4.4 Rewrite `test_controller_asks_one_high_impact_gap_then_switches_to_
  reconnaissance` (encodes the removed behavior) as a local-convergence
  isolation test; all other existing tests unchanged and green.

## 5. Gates and evidence

- [x] 5.1 Full local gates green: pytest (no new failures), ruff check +
  format check, `check_delivery_workflow.py validate`,
  `check_openspec_governance.py`, `build_skill_packages.py --check`.
- [x] 5.2 Regenerate `packages/**` in a generated-only commit.
- [x] 5.3 GitNexus `detect-changes` reconciled with this `impact_scope` via
  `check_impact_scope.py`; reports stored in `evidence/`.
