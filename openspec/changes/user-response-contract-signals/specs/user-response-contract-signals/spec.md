## ADDED Requirements

### Requirement: the persisted user-response class feeds contract-term selection

A small policy table over the persisted prompt-signal classes
(`correction` / `interruption` / `insight` / `answer` / `neutral`) SHALL
map an observed signal plus the outstanding contract terms onto
contract-term adjustments — a `cost_cap` adjustment, `taboos` refresh
(additions and removals), and a `target_gap` directive — reusing the
`turn_contract` seam vocabulary (`RESPONSE_CLASSES`, `CostCap`,
`ContractTerms`) without duplicating or modifying it. The adjustment SHALL
be deterministic and first-match-wins; correction-driven cap adjustments
SHALL never raise an emitted `cost_cap`, while an interruption SHALL raise
the response-production ceiling. `ClarificationPolicy` and the alignment
controller's action vocabulary SHALL be unchanged.

#### Scenario: a correction after an ask lowers the next cost cap and re-opens the corrected node

- **WHEN** a `correction` signal is resolved against contract terms whose
  `target_gap` is the asked node and whose `cost_cap` is unbounded
  generation
- **THEN** the verdict lowers the next cap (bounded response production),
  removes the asked node from taboos (re-open), emits the `reopen`
  directive with the corrected node as the gap target, and types the
  recorded move as `generation`

#### Scenario: a repeated correction drops the ceiling to the one-sentence floor

- **WHEN** a `correction` signal is resolved and the previous signal for
  the run was also a `correction`
- **THEN** the verdict's cost cap is the one-sentence `discrimination`
  floor

#### Scenario: an answer marks the asked node answered and advances target-gap selection away from it

- **WHEN** an `answer` signal is resolved against an outstanding ask
- **THEN** the asked node is added to taboos, the `advance` directive moves
  target-gap selection to the next candidate away from the answered node,
  and the recorded move is `discrimination`

#### Scenario: an interruption redirects target-gap selection toward the new material

- **WHEN** an `interruption` signal is resolved against an outstanding ask
  with candidate nodes available
- **THEN** the `redirect` directive demotes the interrupted node (it is not
  tabooed), target-gap selection resolves toward the next candidate, and
  the cost cap is raised to unbounded generation

#### Scenario: neutral turns leave contract terms unchanged

- **WHEN** a `neutral` signal (or an unclassified turn) is resolved against
  emitted contract terms
- **THEN** the verdict changes no contract term: cost cap unchanged, no
  taboo additions or removals, directive `keep` — no spurious drift

#### Scenario: a correction never raises an emitted cost cap

- **WHEN** a correction row's computed cap is more permissive than the
  emitted cap
- **THEN** the emitted cap is kept (correction adjustments are
  monotone-lowering)

#### Scenario: a correction carrying continuation semantics leaves terms unchanged

- **WHEN** the classified correction's rule carries the `+continuation`
  downgrade (the requester kept the current course)
- **THEN** the verdict changes no contract term and emits the `keep`
  directive

### Requirement: the typed user move is recorded and consumed

On an alignment-phase `UserPromptSubmit`, the lifecycle hook SHALL resolve
the policy verdict against the latest persisted turn record's contract
terms (the turn-record store consumed read-only) and feed a routed
run-scoped record (`route="alignment_user_move"`) carrying the user move
typed in the seam's response classes and the contract-term verdict, so the
alignment-turn-record `user_move` field and contract-term selection at the
seam are fed. The hook SHALL stay fail-open: no verdict is produced outside
the alignment phase, without an active run, or when the record module is
unreachable, and the host session is never blocked. The #503 research
re-entry protocol and the #497 record refresh SHALL be unchanged.

#### Scenario: an alignment-phase prompt feeds the typed user move and verdict to the run surface

- **WHEN** a prompt is submitted on an alignment-phase run whose latest
  turn record carries contract terms
- **THEN** the hook result and sanitized record carry the
  `user_move_policy` verdict with the typed move (a seam response class),
  and a run-scoped `alignment_user_move` record is fed carrying the signal
  class, typed move, and verdict

#### Scenario: outside the alignment phase nothing is fed

- **WHEN** a prompt is submitted without an active run or during a
  non-alignment phase (e.g. research)
- **THEN** no `user_move_policy` verdict is produced and no
  `alignment_user_move` record is fed; the recorded signal and any
  re-entry verdict behave exactly as before

### Requirement: the strategy-selection design comparison is written with a decision

The change's `design.md` SHALL contain a written comparison of (a) a small
policy table over contract-term selection, (b) a bandit for cost-cap
tuning, and (c) a full MDP over interaction history, SHALL name the
decision, and SHALL record the rejected alternatives with rationale.

#### Scenario: the comparison document exists and names the decision

- **WHEN** the openspec change's design document is read
- **THEN** it compares the policy table, the bandit, and the full MDP,
  names the policy table as the decision, and records the bandit
  (deferred) and the full MDP (rejected) as rejected designs
