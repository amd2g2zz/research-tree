## ADDED Requirements

### Requirement: the alignment controller emits contract terms for the next turn

Each alignment `plan()` SHALL emit structured contract terms alongside the
existing decision output — `target_gap` (the alignment-graph node this turn
must advance), `required_traces` (trace-type names from the frozen
`turn_contract` registry), `cost_cap` (the user response-production ceiling
typed as `discrimination` or `generation`), and `taboos` (settled nodes and
nodes whose per-node ask budget or local stagnation excludes them) — without
changing the existing action vocabulary (`ask_one`, `reconnaissance`,
`await_human_confirmation`, `alignment_incomplete`), the `ClarificationPolicy`
surface, or the materialized state shape. The 13-candidate strategy list
SHALL exist only as prompt-layer craft material and SHALL never be added to
the engine vocabulary.

#### Scenario: a plan call emits contract terms ranked from the graph

- **WHEN** the controller plans a turn on a graph with open requester-only
  gaps of different impacts, one of which carries an active divergence axis
  on an ask-exhausted node
- **THEN** the emitted `target_gap` is the node selected by the existing
  divergence-aware ranking (the active-axis node outranks), the
  ask-exhausted non-axis node appears in `taboos`, and the decision still
  carries its `action`, `gap_id`, and `question` keys unchanged

#### Scenario: the user-move redirect is applied via the response policy

- **WHEN** a user-move signal resolves (from the run's persisted
  `alignment_user_move` feed record or an explicit signal) against the
  outstanding ask with candidate nodes available
- **THEN** an interruption redirects `target_gap` selection toward the next
  candidate away from the interrupted node, an answer advances past the
  answered node (which becomes taboo), a correction re-opens the corrected
  node as the target, and the plan output carries the applied
  `user_move_policy` verdict

### Requirement: required traces derive from gap shape and the response-cost class

The emitted `required_traces` SHALL be a deterministic function of the
target gap's shape and the emitted `cost_cap` class, using only trace-type
names registered in the `turn_contract` registry: a proposal-shaped gap
SHALL require `possibility-survey` under a generation cap or `option-set`
under a discrimination cap; a misunderstood-intent gap (a disputed target, or
a correction-driven reopen) SHALL require `guess-statement`. Non-asking
decisions SHALL emit an empty trace gate.

#### Scenario: a proposal-shaped gap requires a survey or option-set trace

- **WHEN** the target gap is an open candidate requester-only point asked
  under an unbounded generation cap
- **THEN** the emitted required traces are exactly `possibility-survey`,
  and the same gap asked under a discrimination cap requires exactly
  `option-set`

#### Scenario: a misunderstood-intent gap requires a guess-statement

- **WHEN** the target node is `disputed`, or the user's correction re-opened
  the asked node
- **THEN** the emitted required traces are exactly `guess-statement`

### Requirement: the cost cap reflects the user-move class

The emitted `cost_cap` SHALL start from the turn's asking shape (unbounded
generation for open-ended elicitation, the one-sentence discrimination cap
for a handoff confirmation) and SHALL be adjusted by the #490
`resolve_user_response_policy` verdict from the observed user-move class: a
correction lowers the ceiling (bounded generation, repeated correction at
the one-sentence discrimination floor) and never raises an emitted cap, an
interruption or insight raises the ceiling to unbounded generation, and a
neutral turn keeps the previous cap.

#### Scenario: a correction lowers the emitted cost cap and a neutral turn keeps it

- **WHEN** the outstanding ask was emitted with an unbounded generation cap
  and the observed signal is a correction, then a repeated correction on the
  following turn, then a neutral turn
- **THEN** the first emission lowers the cap to bounded generation
  (two sentences), the second drops it to the one-sentence discrimination
  floor, and the neutral turn emits the floor unchanged

### Requirement: recorded turns are verified against the emitted terms

`record()` SHALL verify the turn's recorded traces against the last plan's
emitted contract terms via `turn_contract.verify_traces()` before any state
mutation, failing closed with an error naming the exact missing term;
verification SHALL engage only for calls that participate in the protocol by
supplying traces, and legacy calls without traces SHALL keep succeeding. A
turn carrying the required traces SHALL pass, report the satisfied required
terms, and persist the emitted terms, the observed traces, and the typed
user-response class on the turn's event and in the #497 turn record.

#### Scenario: a recorded turn missing a required trace fails naming the term

- **WHEN** a turn is recorded with no traces after a plan emitted a
  `possibility-survey` requirement
- **THEN** the record fails with a missing-trace error naming
  `possibility-survey` and no state mutation is persisted

#### Scenario: a recorded turn carrying the traces persists terms, traces, and user move

- **WHEN** a turn is recorded with the required traces and the typed user
  move, and the canonical loop appends the #497 turn record with the emitted
  terms, the traces, and the user move
- **THEN** the record passes, reports the satisfied required terms, the
  turn's event carries the traces and user move, and the persisted turn
  record reads back with the same contract terms, traces, and user move
