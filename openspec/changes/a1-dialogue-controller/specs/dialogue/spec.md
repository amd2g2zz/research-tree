## ADDED Requirements

### Requirement: four-way routing per utterance

#### Scenario: each way routes per the matrix
- **WHEN** utterances of kind preference / claim / guess / branch are ingested
- **THEN** they land respectively in slots, the claim ledger, the hypothesis ledger, and the parking lot

### Requirement: guessed constraints carry the discrimination question and relax on answer

#### Scenario: guessed constraint registered
- **WHEN** a guessed constraint is ingested
- **THEN** it is queryable with the discrimination question attached

#### Scenario: estimate answer relaxes to intent
- **WHEN** the discrimination answers "estimate"
- **THEN** the constraint becomes a slot (intent) and leaves the guessed set

#### Scenario: deployment-fact answer hardens
- **WHEN** the discrimination answers "deployment-fact"
- **THEN** the constraint joins the hard set

### Requirement: corrections route the same way (no privileged channel)

#### Scenario: three correction kinds
- **WHEN** preference-change / private-fact / guess-restated corrections arrive
- **THEN** they route respectively to slots (+ consequence map), the claim ledger, and hypothesis re-review (status on_trial)

### Requirement: echo confirmation triggers only for signed-thing changes

#### Scenario: three change classes trigger
- **WHEN** a deconstruction changes kill conditions, the feasibility menu, or the verdict structure
- **THEN** echo confirmation is required; ordinary deconstructions do not trigger it

### Requirement: convergence is computed C1-C5

#### Scenario: hard gates
- **WHEN** C1 (problem shaped) ∧ C2 (≥3 key slots) ∧ C3 (make-or-break identified) hold
- **THEN** converged is true with per-condition flags

#### Scenario: pace signals
- **WHEN** new-claim counts decay between turns
- **THEN** C4 reflects the decay; a corrected restatement flips C5 false

### Requirement: divergence proposes terrain, contained branches never punish

#### Scenario: sustained divergence
- **WHEN** parking-lot branches ≥3 with ≤1 claim
- **THEN** the divergence check proposes an upstream terrain comparison
