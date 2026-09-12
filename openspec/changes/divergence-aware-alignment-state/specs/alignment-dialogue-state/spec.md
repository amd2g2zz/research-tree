## ADDED Requirements

### Requirement: divergence axes are first-class persisted state

The alignment store SHALL persist divergence axes as first-class rows (a
`divergence_axes` table with per-axis stagnation and an `open`/`converged`
lifecycle), anchored to a graph node, declarable at `record()` time via
`new_axes` (a description string or an `{"id"?, "description"}` object).
Generated axis ids SHALL be deterministic (`axis-` + a digest of node id and
description) so re-declaring the same direction touches the existing axis
instead of forking; an explicit id belonging to another node SHALL be
rejected. Axis state SHALL be serialized inside the materialized state
(`state["divergence"]["axes"]`) with per-node stagnation alongside
(`state["divergence"]["node_stagnation"]`), outside the graph digest, and
SHALL survive both a store reopen and an event-log rebuild.

#### Scenario: a user answer opens a new divergence axis

- **WHEN** `record()` is called for a node with `new_axes` declaring an
  unexplored direction
- **THEN** the axis is persisted with `status="open"`, a deterministic
  `axis_id`, `stagnant_turns=0`, and the turn it was opened on
- **AND** the recorded node's stagnation is reset and the record result
  reports the opened axis and a `divergent` dialogue mode

#### Scenario: axis state survives a persistence round-trip

- **WHEN** a store with declared axes and stagnant nodes is reopened from
  its database, or its event log is replayed via `rebuild_materialized()`
- **THEN** the axes and per-node stagnation are restored with identical
  field values

#### Scenario: re-declaration is idempotent and cross-node ids are rejected

- **WHEN** the same direction is re-declared on the same node
- **THEN** the existing axis is touched, not forked
- **WHEN** an explicit axis id belonging to a different node is declared
- **THEN** the record is rejected naming the conflict

### Requirement: a new divergence axis keeps the controller in dialogue

The controller SHALL treat an *active* axis (`open` with
`stagnant_turns` below the per-axis stall threshold) as a reason to stay in
dialogue: `record()` SHALL NOT return `reconnaissance` while an active axis
or an explorable requester-only node exists, and `plan()` SHALL return an
exploratory `ask_one` on the axis-bearing node — naming `axis_id` and the
axis description — even when that node's ask budget under
`MAX_ASKS_PER_NODE` is spent (an active axis grants additional ask
allowance; the budget bounds re-asking one dimension, not new dimensions).

#### Scenario: a quiet-on-graph answer that opens a new dimension stays in dialogue

- **WHEN** the user's answer changes nothing on the graph but the record
  declares a new divergence axis, even after the node's ask budget is spent
- **THEN** the record result's `next_action` is `plan`, not
  `reconnaissance`
- **AND** the next `plan()` decision is `ask_one` naming the axis

### Requirement: convergence state is tracked per node and per axis

Stagnation SHALL be tracked per node (`nodes.stagnant_turns`) and per axis,
not as a single global consecutive-turn counter; a quiet record stagnates
the recorded node and its open axes, and answered/changed/reopened outcomes
reset the node's stagnation (`answered` additionally converges the node's
open axes; `reopened` re-opens converged ones). The controller's legacy
global `stagnant_turns` SHALL be a derived reporting maximum only, and no
plan decision SHALL be driven by it. Local convergence in one area SHALL
NOT terminate exploration in another: while any requester-only node is
below the stall threshold or any axis is active, `plan()` SHALL NOT return
`reconnaissance` because of stagnation.

#### Scenario: stagnation localized in one node does not stop another node

- **WHEN** one requester-only node has stalled at the per-node threshold and
  another requester-only node has not been explored
- **THEN** `plan()` returns `ask_one` on the explorable node, not
  `reconnaissance`

#### Scenario: two quiet turns no longer force an exit

- **WHEN** two consecutive records change nothing on the graph while an
  explorable node or active axis exists
- **THEN** the controller remains in dialogue (`next_action` and `plan()`
  are not `reconnaissance`)

### Requirement: a genuine stall moves to agent-side reconnaissance

When no active axis exists and every requester-only candidate node is
locally stalled, the dialogue mode SHALL be `stalled`: `record()` SHALL
return `next_action: "reconnaissance"` and `plan()` SHALL return
`reconnaissance` with a stall reason. A later divergence-axis declaration
on a stalled node SHALL re-open the dialogue (reset the node's stagnation
and make the node axis-eligible again).

#### Scenario: all requester-only points stalled with no axes

- **WHEN** every requester-only candidate node is at the per-node stall
  threshold and no axis is active
- **THEN** `record()` reports a `stalled` dialogue mode with
  `next_action: "reconnaissance"` and `plan()` returns `reconnaissance`
  naming the stall

#### Scenario: a stalled dialogue re-opens on divergence

- **WHEN** a new axis is declared on a stalled node
- **THEN** the node's stagnation resets and `plan()` returns an exploratory
  `ask_one` on the axis
