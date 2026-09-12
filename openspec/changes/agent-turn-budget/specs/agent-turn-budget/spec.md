## ADDED Requirements

### Requirement: contract terms carry the agent turn budget

Each emitted `contract_terms` SHALL carry an `agent_turn_budget` —
`max_questions` per interactive turn and `max_chars` per turn, with named
exported defaults (`DEFAULT_MAX_QUESTIONS_PER_TURN = 1`,
`DEFAULT_MAX_CHARS_PER_TURN = 1200`) — and terms without the new fields
SHALL keep parsing (additive schema).

#### Scenario: the budget is emitted with the contract terms

- **WHEN** the controller plans any turn that emits contract terms
- **THEN** the emitted terms carry `agent_turn_budget` with the default
  question and character budgets

#### Scenario: legacy terms without budget fields still parse

- **WHEN** a persisted decision's terms contain only the five original
  contract-term fields
- **THEN** `ContractTerms.from_dict` parses them with
  `agent_turn_budget` absent (`None`) and an empty deferral queue

### Requirement: recorded turns are verified against the agent turn budget

When the persisted terms carry a budget, a recorded turn exceeding
`max_questions` or `max_chars` SHALL be a named violation returned as
`turn_budget_violations` in the record result and the persisted event
details — flag-not-block: the turn remains valid as continuity grounding,
and each violation names the exceeded dimension, the limit, and the
observed value so discipline telemetry can count it.

#### Scenario: more than one question in a turn names the question dimension

- **WHEN** a turn is recorded with two questions against a budget of
  `max_questions = 1`
- **THEN** the record result and event details carry a
  `turn_budget_violations` entry with dimension `max_questions`,
  the recorded turn stays valid, and no exception is raised

#### Scenario: an over-length turn names the character dimension

- **WHEN** a turn is recorded with more characters than `max_chars`
- **THEN** the violations name dimension `max_chars` with the limit and
  the observed length

#### Scenario: a within-budget turn reports no violations

- **WHEN** a turn is recorded within both budget dimensions
- **THEN** `turn_budget_violations` is empty (or absent for terms without
  a budget)

### Requirement: required traces queue at most two per turn

The emission SHALL compose required traces in priority order (carried
deferrals first, then gap-shape and novice-posture requirements), emit at
most 2 as `required_traces`, and carry the remainder in the emitted terms
as `deferred_traces`; the next turn's terms SHALL re-emit deferred traces
as required. Nothing is silently dropped.

#### Scenario: a three-trace wishlist defers the remainder

- **WHEN** the composed wishlist for a turn holds three required traces
- **THEN** the emitted terms require exactly the two highest-priority
  names and carry the third in `deferred_traces`

#### Scenario: deferred traces are re-emitted as required next turn

- **WHEN** the previous terms carried a deferred trace and the next turn's
  terms are emitted
- **THEN** the deferred name reappears among that turn's `required_traces`
  (within the two-per-turn cap), ahead of newly derived names

### Requirement: the per-turn question budget gates asks

Asks SHALL consume the per-turn question budget, visible in the decision's
`question_budget` disposition; when the budget is exhausted, `plan()`
SHALL emit a non-question decision (the mirror/teach/gather postures via
the existing action vocabulary) until `record()` advances the turn and
resets the budget. Per-node `MAX_ASKS_PER_NODE` semantics are unchanged.

#### Scenario: budget exhaustion forces a non-question decision

- **WHEN** a turn already emitted its ask and `plan()` runs again before
  the turn is recorded
- **THEN** the decision carries no question (`question: None`), keeps the
  dialogue gap target, and shows the exhausted `question_budget`
  disposition instead of consuming another node's ask

#### Scenario: recording the turn resets the per-turn budget

- **WHEN** the turn is recorded and the controller plans the next turn
- **THEN** the next ask is emitted normally with a fresh question budget
