# Design: divergence-aware-alignment-state

## Context

Issue #496: alignment was modeled as linear convergence — a global
`stagnant_turns` counter (`MAX_STAGNANT_TURNS = 2`) and the global turn
counter mechanically switched the controller to `reconnaissance` exactly when
a user answer opened a new dimension worth exploring. User ruling: 整个对齐
并不是线性收敛过程，而是先发散、局部收敛、再发散. The engine must represent
the difference between an *accidental stall* (nothing new, no new axis →
agent-side reconnaissance is acceptable) and a *deliberate divergence* (the
user's input implied an unexplored direction → stay in dialogue), and must
track convergence per node/per axis so local convergence in one area never
terminates exploration in another. This change is engine-side only; #489
will consume the axis state to rank `target_gap` and wire contract emission
(`turn_contract.py` stays unwired), #491 replaces the remaining turn-cap
exit.

## Goals / Non-Goals

**Goals:**

- First-class, serializable, queryable divergence-axis state persisted in the
  alignment SQLite store (existing event-sourced + materialized-view pattern).
- Per-node and per-axis stagnation; removal of the global stagnation escape.
- STALL vs NEW-DIVERGENCE-AXIS distinction surfacing in `plan()` decisions and
  `record()` results.
- Contained blast radius: all state-shape changes additive; graph-digest
  semantics unchanged.

**Non-Goals:**

- #491: alignment score, `alignment_incomplete`, `MAX_TURNS` exit policy —
  untouched; the turn-cap reconnaissance branch stays verbatim.
- #489/#490: contract emission, response classification, `turn_contract.py`
  wiring — the divergence state is delivered queryable but unconsumed.
- SKILL prose / `skill-src/**` / `references/**` (owned by #489/#500);
  `packages/**` only mechanically regenerated (generated-only commit).
- Any prompt-layer guidance about *how* to explore an axis (ADR-008: behavior
  is not enumerated; the engine gates structure only).

## impact_scope

Index rebuilt via `node .gitnexus/run.cjs analyze .` in the #496 worktree at
branch tip `c95c183` (14,887 nodes / 30,195 edges) before any edit; impact
run upstream per symbol; detect-changes reconciliation stored in `evidence/`
before push.

| Symbol / file | Status | Risk | Upstream callers (from impact) |
|---|---|---|---|
| `AlignmentGraphStore.record` | modified | LOW (6 impacted) | module `record` wrapper, CLI `main`; flows: main |
| `AlignmentGraphStore.plan` | modified | LOW (6 impacted) | module `plan` wrapper, CLI `main` |
| `AlignmentGraphStore.initialize` | modified | LOW (6 impacted) | module `init`, CLI `main` |
| `AlignmentGraphStore._create_schema` | modified | LOW (4 impacted) | `initialize` |
| `AlignmentGraphStore._materialize` | modified | **CRITICAL** (17 impacted) | `_commit_event`, `confirm`, `plan`, `status`; transitively `merge`, `record`, `compile_handoff`, `rebuild_materialized`, `alignment_handoff.initialize_research_from_alignment`, `cli._strategy_confirm`; flows: init/main/plan/record/confirm |
| `AlignmentGraphStore._restore_state` | modified | LOW (3 impacted) | `rebuild_materialized` |
| module `record`, CLI record parser | modified | LOW | tests, CLI users |
| `tests/test_alignment_divergence.py`, `tests/test_alignment_controller.py` | added/modified | LOW | pytest collection |
| `packages/**` | regenerated | LOW (generated) | parity gate |

**CRITICAL warning (per AGENTS.md):** `_materialize` is the state-projection
hub. Containment: only *additive* keys; per-node stagnation and axes live in
a new top-level `state["divergence"]` object *outside* `graph`, so
`graph_digest` composition is untouched and the two external consumers
(unpack `compile_handoff` output; neither inspects `stagnant_turns`) are
unaffected.

## Decisions

### One dialogue mode, computed from per-node/per-axis state

`_dialogue_mode(nodes, axes)` → `handoff_ready` (readiness ready; plan() will
draft the handoff) > `divergent` (≥1 *active* axis) > `converging` (some
requester-only candidate/disputed node below the stall threshold) > `stalled`
(everything requester-only is locally stalled, no active axis). `record()`
returns `next_action` = `reconnaissance` only for `stalled`; `plan()` uses the
same axes/node state for its decision. STALL ⇒ agent-side reconnaissance
acceptable; DIVERGENT ⇒ stay in dialogue with an exploratory move.

### Divergence axes: caller-declared, node-anchored, deterministic ids

The engine never classifies user input (#490 owns that); `record(...,
new_axes=...)` accepts caller-declared axes — a description string or
`{"id"?, "description"}` (whitelist validation, repo pattern). An axis is
anchored to the recorded node (the only anchor `record()` has; attribution
beyond that is #489/#490's job). Explicit ids must match the node-id shape
and belong to the recorded node; generated ids are
`axis-<sha256(node_id, description)[:12]>` so re-declaring the same direction
touches (idempotent) instead of forking. Serialized shape per axis:
`{axis_id, node_id, description, status, opened_turn, last_turn,
stagnant_turns, created_at, updated_at}`.

### Axis lifecycle and per-axis stagnation

`status` ∈ `{"open", "converged"}` (`AXIS_STATUSES`). Opening sets
`opened_turn`/`last_turn`, resets the node's stagnation (declaring a new
direction is the opposite of a stall). A quiet record (no graph change, no
new axis) stagnates the node and its open axes; `answered` converges the
node's open axes (the answer settles the question the axis hangs on) unless
the same record re-declares them; `reopened` re-opens converged axes.
*Active* = `open` and `stagnant_turns < MAX_STAGNANT_TURNS`; only active axes
make a node divergent-eligible. The model is self-bounding: an axis that
stays quiet across the threshold stops counting — no global escape needed.

### MAX_STAGNANT_TURNS repurposed; MAX_ASKS_PER_NODE kept; MAX_TURNS untouched

`MAX_STAGNANT_TURNS = 2` is redefined as the **per-node/per-axis stall
threshold** — the mechanical *global* exit it used to drive is deleted.
`MAX_ASKS_PER_NODE = 2` keeps its semantics as the bound on re-asking one
dimension; the documented natural supersession is that an **active axis
grants additional ask allowance on its node** — a newly opened dimension is
not a repeated question, so the budget cannot foreclose it (per-axis
stagnation still bounds it). `MAX_TURNS = 6` and the turn-cap branch stay
verbatim for #491 to replace with the alignment-score exit policy.

### Per-node stagnation lives on `nodes`; global counter demoted to derived

`nodes` gains `stagnant_turns` (same treatment as `ask_count`: preserved on
upsert, restored on rebuild). `controller.stagnant_turns` is recomputed as
the **maximum across nodes** — informational only, no decision reads it.
`record()` returns `stagnant_turns` for the *recorded node* (the locally
meaningful value).

### Serialization for #489, outside the graph digest

Materialized state gains one top-level object:
`"divergence": {"mode": <str>, "axes": [axis...], "node_stagnation":
{node_id: int}}`. Axes and node stagnation stay out of `graph`, so
`graph_digest` keeps meaning *graph content* — handoff confirmation digests
and `_invalidate_handoff_if_confirmed` semantics are unchanged. `graph`
node/edge dicts are byte-identical in shape to before. `AXIS_STATUSES`,
`DIALOGUE_MODES`, and the axis schema are module-level public surface; the
CLI `record` command accepts repeatable `--axis <description>`.

### Persistence follows the existing event-sourcing pattern

`SCHEMA` 2 → 3 (per-run databases are ephemeral; same bump convention as
before). New `divergence_axes` table (FK → nodes); `_commit_event` snapshots
the whole materialized state (axes included) into `state_json`;
`_restore_state` and `rebuild_materialized` restore axes and node stagnation
(axes deleted before nodes for FK order). Round-trip = reopen the store or
replay the event log; both covered by tests.

## Rejected Designs

- **Fixed primitive menus for divergence handling** (an enum of
  divergence/stall/exploration actions the engine selects from): the ADR-008
  rejected design — behavior is not enumerated in engine vocabulary; the
  engine tracks state and gates structure, the prompt layer composes moves.
- **Ladder rules** (fixed staged sequences like ask→echo→survey): same
  rejection; a ladder is a menu with ordering.
- **Bigger lookup tables** (more reason/threshold tables keyed on outcome
  combinations): scales linearly with shape complexity and still cannot
  represent "this node diverged, that one stalled"; per-node/per-axis state
  represents it exactly.
- **Axis-aware resets on the global stagnation counter** (keep one global
  counter, reset it when an axis opens): still a linear-convergence model in
  disguise — one node's state would gate decisions about every other node.
- **Folding axes into node `attributes_json`**: not first-class (no FK, no
  per-axis stagnation columns), and #489 would have to parse opaque blobs to
  rank `target_gap`.
- **New `plan()` action enum value `explore_axis`**: breaks every consumer
  matching on the existing action set and re-encodes behavior naming in the
  engine; `ask_one` + additive `axis_id`/`axis` fields carry the same signal.
- **Per-node stagnation inside graph node dicts**: would change
  `graph_digest` semantics on quiet records and perturb the CRITICAL-blast
  handoff-digest path for no benefit.
- **Removing `MAX_TURNS` now**: owned by #491; removing it here would leave
  the dialogue with no bound at all in the stall case.

## Risks / Trade-offs

- [_materialize blast radius (CRITICAL)] -> additive-only keys; graph digest
  composition untouched; both external consumers verified to not inspect the
  changed surface; detect-changes reconciliation before push.
- [Caller declares spurious axes] -> axes are bounded (stagnation threshold),
  per-node ask budget still applies to non-axis asks, and axis quality is
  #490/#489's classification problem; the engine only records and measures.
- [Axis anchored to a node that later resolves] -> eligibility already gates
  on `candidate`/`disputed`, so a resolved node's axes become dormant
  naturally; state remains queryable for #489.
- [Generated packages carry the new engine copy] -> regenerated in a
  generated-only commit via `build_skill_packages.py`; parity gate enforced.

## Migration Plan

No live data migration: alignment databases are per-run and `SCHEMA` gates
open (`_require_schema` rejects `2` after the bump, same as every prior bump).
Events recorded by the new code round-trip through `rebuild_materialized`.
#489 consumes `state["divergence"]` read-only; no API removal, so nothing to
migrate downstream.
