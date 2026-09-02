## ADDED Requirements

### Requirement: the turn cap blocks instead of exiting

Reaching `MAX_TURNS` while the alignment score is below the exit threshold
SHALL produce the explicit blocked disposition `alignment_incomplete` — never
a strategy switch to `reconnaissance`. The disposition SHALL name every open
requester-only gap (`blocked_nodes`, with impact and whether its ask budget is
spent), the open divergence axes, and the alignment score versus
`ALIGNMENT_SCORE_EXIT_THRESHOLD`, and SHALL require the user to either extend
the dialogue or record an explicit waive.

#### Scenario: turn cap with open high-impact gaps names them and never escapes

- **WHEN** the turn counter reaches `MAX_TURNS` while a high-impact
  requester-only gap is unresolved (the user having kept answering, opening a
  new divergence axis each turn)
- **THEN** `plan()` returns `action == "alignment_incomplete"`, not
  `reconnaissance`
- **AND** `blocked_nodes` names the gap, `exhausted_ask_nodes` names the spent
  ask budget, and `alignment_score` is below `alignment_exit_threshold`

#### Scenario: a user response after the block extends the dialogue

- **WHEN** the user records a response after an `alignment_incomplete`
  disposition
- **THEN** the dialogue re-opens (`plan()` returns `ask_one`) for
  `ALIGNMENT_EXTENSION_TURNS` further turns
- **AND** past that window the blocked disposition returns and a fresh user
  response is required to extend again

### Requirement: alignment exit is gated by a deterministic score

The controller SHALL compute a deterministic alignment score (integer
0..`ALIGNMENT_SCORE_MAX`) from graph state — impact-weighted open
requester-only gaps, spent `MAX_ASKS_PER_NODE` budgets on open gaps, and open
divergence axes — with the weights and `ALIGNMENT_SCORE_EXIT_THRESHOLD` as
named, documented module constants. Offering the handoff (`plan()` returning
`await_human_confirmation`) and accepting it (`confirm()`) SHALL require the
score to reach the threshold or a valid waive; a below-threshold score under
user pressure SHALL raise a below-the-exit-threshold error.

#### Scenario: a satisfied score allows the normal handoff path

- **WHEN** the alignment graph is structurally ready with no open gap, spent
  ask budget, or open axis
- **THEN** the score equals the threshold and `plan()` offers the handoff

#### Scenario: a low score blocks even under user pressure

- **WHEN** the graph is structurally ready but an open divergence axis on a
  settled node keeps the score below the threshold
- **THEN** `plan()` stays in dialogue with an exploratory `ask_one` on the
  axis-bearing node, and `confirm()` raises the below-threshold error instead
  of accepting the handoff

### Requirement: exhausted high-impact asks escalate instead of being abandoned

When a requester-only gap's ask budget is spent at high impact
(`ALIGNMENT_HIGH_IMPACT`) and no dialogue move remains, the controller SHALL
return `alignment_incomplete` naming that gap (in `blocked_nodes` and
`exhausted_ask_nodes`) instead of the stall/agent-verifiable reconnaissance,
and `record()` SHALL report `next_action: "alignment_incomplete"` for the same
state. An active divergence axis on the node SHALL keep the node askable first
(#496 extra allowance composes), and gaps that are stalled but not
ask-exhausted keep the #496 stall reconnaissance.

#### Scenario: a high-impact gap with a spent ask budget is named, not abandoned

- **WHEN** two asks on a high-impact requester-only gap changed nothing and no
  other node is askable
- **THEN** `plan()` returns `alignment_incomplete` naming the gap and its
  spent ask budget, not `reconnaissance`

### Requirement: an explicit waive re-opens the exit until the graph changes

`AlignmentGraphStore.waive(reason)` SHALL record an explicit user waive
(rejecting empty and generic-acknowledgement reasons) bound to the graph
digest at waive time. While that digest is current, a below-threshold score
SHALL NOT block `plan()`'s handoff offer or `confirm()`'s acceptance; any
later graph change SHALL expire the waive and re-engage the gate. Without a
recorded waive the below-threshold exit stays blocked.

#### Scenario: waive records, proceeds, and expires on graph change

- **WHEN** the user records an explicit waive after an
  `alignment_incomplete` disposition
- **THEN** `plan()` proceeds past the blocked disposition
- **WHEN** the alignment graph changes afterwards
- **THEN** the stale waive no longer unlocks the exit and the blocked
  disposition returns
