## ADDED Requirements

### Requirement: the engine gates on structural traces, never on enumerated behavior

The two-layer contract SHALL split responsibility as follows: the engine
layer (runtime) gates ONLY on structural traces — state persistence and
continuity (#497), phase discipline (#492), turn-shape measurement (#493),
composition checks (#499), and structural-trace gates that verify *that a
trace exists*, never *what it says*; the prompt layer (SKILL + references)
carries ALL open-ended behavior strategy (interview craft, teaching,
counterexamples, persona) as craft guidance, not as engine-checklistable
items. The enumerated space SHALL be limited to contract terms and trace
types; behaviors SHALL never be enumerated. Design test for any future
proposal: adding an enum entry for something the model should say violates
the contract; adding a trace type the engine can verify conforms.

#### Scenario: a contract-conforming extension

- **WHEN** a proposal adds a verifiable structural trace type (for example
  `proportionality_assessment`, #498) to the registry and gates on its
  presence and schema
- **THEN** the extension conforms to the two-layer contract

#### Scenario: a contract-violating extension

- **WHEN** a proposal adds an engine enum entry for something the model
  should say (for example a `teach` action in a fixed policy vocabulary, or a
  fixed selection ladder over guidance moves)
- **THEN** the proposal violates the two-layer contract and SHALL be rejected
  in favor of a prompt-layer craft document plus, where load-bearing, an
  engine-side structural trace gate

### Requirement: the engine emits contract terms for the next turn

The engine's per-turn policy job SHALL be contract emission of structured
terms: `target_gap` (the alignment-graph node this turn must advance),
`required_traces` (a finite set of registered trace types the turn must
leave), `cost_cap` (a user response-production ceiling distinguishing
discrimination responses — capped at one sentence pointer (一句指认) — from
generation responses, which may carry free text), and `taboos` (nodes already
answered / asks already spent). The canonical loop SHALL be: emit contract
terms → prompt layer composes the turn freely (infinite generation space) →
engine verifies traces against terms → persist the turn-record (#497).

#### Scenario: contract terms serialize strictly

- **WHEN** a `ContractTerms` mapping is deserialized that is missing a field
  or carries an unknown field
- **THEN** validation rejects it naming the offending field

#### Scenario: a discrimination cost cap is bounded to one sentence

- **WHEN** contract terms declare a `cost_cap` of class `discrimination`
- **THEN** the cap is exactly one sentence, and any other sentence bound for
  that class is rejected; class `generation` allows free text

#### Scenario: taboos reference alignment-graph nodes

- **WHEN** contract terms declare `taboos` or a `target_gap`
- **THEN** every entry matches the alignment-graph node-id shape and taboo
  entries are unique

### Requirement: trace types form a frozen, append-only registry

The trace-type registry SHALL be frozen data with append-only semantics,
seeded with exactly the six initial types: option-set, concept-card,
guess-statement, counterargument, possibility-survey, evidence-delta.
Registering a name that already exists SHALL be rejected; there SHALL be no
unregister or redefine path. Each trace type SHALL declare the required
fields of its payload so verification can perform presence and schema checks.

#### Scenario: the registry seeds exactly the six initial types

- **WHEN** the default registry is inspected
- **THEN** it contains exactly option-set, concept-card, guess-statement,
  counterargument, possibility-survey, and evidence-delta

#### Scenario: duplicate registration is rejected

- **WHEN** a trace type is registered whose name already exists in the
  registry
- **THEN** registration fails with a named duplicate error and the existing
  registry is unchanged

### Requirement: verify_traces fails closed naming the missing term

`verify_traces` SHALL check the turn's recorded traces against the emitted
contract terms using presence and schema checks only: every required trace
type MUST be present among the recorded traces, every recorded trace type
MUST be registered, and every required trace's payload MUST carry the type's
declared required fields. A missing required trace SHALL fail with an error
naming the exact missing term. `verify_traces` SHALL NOT inspect content
quality, wording, or any quality beyond the declared structural fields.

#### Scenario: a missing required trace is named

- **WHEN** the contract requires a `possibility-survey` trace and the turn
  recorded no trace of that type
- **THEN** verification fails with `MissingTraceError` naming
  `possibility-survey`

#### Scenario: a malformed trace payload is rejected

- **WHEN** a recorded trace of a required type lacks a declared required
  field, or its type is not registered
- **THEN** verification fails with a schema error naming the offending field
  or type

#### Scenario: a satisfied contract verifies without content judgment

- **WHEN** every required trace is present with well-formed structural
  fields, regardless of the payload text's quality
- **THEN** verification succeeds and returns the satisfied required traces
