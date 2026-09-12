# Proposal: divergence-aware-alignment-state

## Why

Issue #496 (bug, user ruling 2026-09-02): the alignment controller assumes
alignment converges monotonically — every turn should change the graph, and
when it stops changing the right move is to *leave the dialogue*. Real
alignment is 发散 → 局部收敛 → 再发散: a user answer that changes nothing on
the graph may open a *new* divergence axis worth exploring *in dialogue*.
`MAX_STAGNANT_TURNS = 2` plus the global turn counter mechanically exit the
dialogue exactly when it was about to get interesting
(`alignment_graph.py:399` — `"reconnaissance" if stagnant >= MAX_STAGNANT_TURNS else "plan"`).

## What Changes

1. **Divergence axes become first-class persisted state** (SQLite `SCHEMA`
   2 → 3, new `divergence_axes` table following the existing event-sourced +
   materialized-view pattern): an axis is a user-implied unexplored direction
   anchored to a graph node, declared by the caller at `record()` time
   (`new_axes`), with deterministic ids (`axis-<sha12>` of node + description,
   or caller-supplied), dedupe on re-declaration, per-axis stagnation
   tracking, and an `open`/`converged` lifecycle.
2. **Convergence state is tracked per node and per axis**, not as one global
   turn counter: `nodes` gains a `stagnant_turns` column; the controller's
   global `stagnant_turns` survives only as a derived maximum (reporting,
   no longer decision-driving).
3. **Stagnation escape is removed.** `plan()` no longer returns
   `reconnaissance` because two global consecutive turns were quiet. It now
   distinguishes (a) STALL — nothing new AND no active divergence axis on any
   requester-only point → agent-side reconnaissance is acceptable; from
   (b) NEW DIVERGENCE AXIS — an active axis exists → stay in dialogue with an
   exploratory move (`ask_one` naming the axis, granted its own ask allowance).
   Local convergence in one node never terminates exploration of another
   node's axis. `MAX_TURNS` and the readiness/turn-cap branches are untouched
   (the turn-cap exit policy is #491's scope).
4. **Serializable, queryable state for #489**: materialized state gains a
   top-level `divergence` object — `{"mode": <handoff_ready|divergent|
   converging|stalled>, "axes": [...], "node_stagnation": {...}}` — outside
   the graph digest; `record()` returns additive `dialogue_mode` and
   `opened_axes` keys; `ask_one` decisions may carry `axis_id`/`axis`.
   `turn_contract.py` stays unwired (#489 owns emission wiring).
5. Engine-side only: no SKILL prose changes (owned by #489/#500);
   `packages/**` regenerated mechanically in a generated-only commit.

## Capabilities

### New Capabilities

- `alignment-dialogue-state`: the divergence-aware alignment state model —
  per-node/per-axis convergence tracking, divergence-axis persistence and
  lifecycle, and the STALL-vs-DIVERGENT plan decision contract.

### Modified Capabilities

- None.

## Impact

- `src/research_tree/alignment_graph.py` (owned file): `SCHEMA` bump,
  `AlignmentGraphStore.initialize/_create_schema/_materialize/_restore_state/
  rebuild_materialized/plan/record`, module-level `record`, CLI `record`
  subparser, new module constants. GitNexus impact: `record`/`plan`/`initialize`
  LOW (6 impacted each); `_materialize` **CRITICAL** (17 impacted — hub for
  `plan`/`record`/`confirm`/`status`/`compile_handoff` and, downstream,
  `alignment_handoff.initialize_research_from_alignment` and
  `cli._strategy_confirm`); blast radius contained by keeping all state-shape
  changes additive and outside the graph digest. HIGH/CRITICAL flagged per
  AGENTS.md; reconciliation in `evidence/`.
- `tests/test_alignment_divergence.py` (new), `tests/test_alignment_controller.py`
  (one test rewritten — it encoded the removed linear-convergence escape;
  justified in the PR body).
- Out of scope: #491 (exit policy / `alignment_incomplete`), #489 (contract
  emission), #490 (response classification), SKILL prose, `skill-src/**`,
  `references/**`, `turn_contract.py` wiring.
