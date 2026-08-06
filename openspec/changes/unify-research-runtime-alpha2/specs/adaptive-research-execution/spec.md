## ADDED Requirements

### Requirement: Research actions target explicit Decision Slot deficits
The system SHALL generate bounded landscape, deep-dive, adversarial, validation, or method-switch actions from an open Decision Slot, its evidence deficit, closure oracle, dependencies, and prior outcomes.

#### Scenario: A broad Decision Slot has no evidence map
- **WHEN** a Decision Slot has no verified Finding Packs
- **THEN** the policy proposes a landscape action with required evidence classes and a completion oracle

#### Scenario: Evidence conflicts on a consequential option
- **WHEN** an Insight Digest marks a Slot contested
- **THEN** the policy prioritizes an adversarial or independent-method action before decision convergence

### Requirement: Research growth is triggered by verified state change
The system SHALL grow depth, breadth, correction, validation, or method-switch successors only from a referenced finding, failed oracle, newly exposed uncertainty, competing hypothesis, invalidated premise, or unavailable method.

#### Scenario: Finding exposes a narrower unresolved question
- **WHEN** a verified Finding Pack identifies a decision-relevant uncertainty and closure oracle
- **THEN** the policy creates a child action linked to the triggering finding and missing evidence

#### Scenario: Worker returns generic suggestions without evidence
- **WHEN** a worker proposes additional topics without a triggering evidence reference or closure deficit
- **THEN** the policy rejects those proposals as unbounded growth

#### Scenario: First-wave material is relevant but shallow

- **WHEN** batch assessment shows useful sources but insufficient primary evidence, implementation detail, or oracle readiness
- **THEN** the policy grows a deep-read, repository-inspection, adversarial, or experiment action tied to the missing dimension

### Requirement: Invalidated research directions create successor strategies

When evidence contradicts a material premise or shows that the current strategy is superficial, the system SHALL persist a pivot assessment, supersede affected pending actions, create a successor strategy and Research Action Graph, and retain causal lineage to the invalidating evidence.

#### Scenario: Research reveals the initial architecture assumption is wrong

- **WHEN** accepted evidence invalidates that assumption after handoff
- **THEN** the coordinator autonomously replans within confirmed authority and records the pivot for delivery instead of continuing the stale plan or silently replacing it

#### Scenario: Pivot changes requester-controlled intent or safety

- **WHEN** the required successor would alter outcome, authority, safety boundary, or an explicit hard constraint
- **THEN** the run becomes authority_blocked and asks one focused human question rather than assuming permission

### Requirement: Realized delta measures closure-relevant change
The system SHALL initialize historical evidence at zero realized delta and SHALL measure new evidence-class coverage, provenance independence, contradiction state, oracle state, implementation uncertainty, and Decision Slot closure change after each ingestion.

#### Scenario: New Finding Pack repeats known claims and provenance
- **WHEN** a fresh artifact adds no new closure-relevant state
- **THEN** realized delta is zero and a no-state-change penalty is recorded

### Requirement: Pruning is conservative and reversible
The system SHALL mark optional duplicate, dominated, superseded, decision-neutral, or repeatedly unproductive actions as deferred with a reason and SHALL NOT delete their evidence history.

#### Scenario: Optional branches ask the same question
- **WHEN** two optional frontier actions target the same Slot, method, oracle, and normalized question
- **THEN** the lower-value action is marked dominated and references the retained action

#### Scenario: Low-scoring P0 validation remains open
- **WHEN** mandatory counterevidence or validation has low expected value but is required for P0 closure
- **THEN** it remains eligible and cannot be pruned solely by score or frontier capacity

### Requirement: Research stops only at explicit batch, Slot, and run boundaries
The system SHALL distinguish batch checkpoint, Decision Slot closure, and run completion and SHALL NOT treat an empty static task list, worker return, completed wave, or report existence as a successful stop.

#### Scenario: Current frontier drains with an unclosed Slot
- **WHEN** no action is currently executable but closure obligations remain
- **THEN** the coordinator records a blocker, method switch, deferred fallback, or authority boundary rather than completion

### Requirement: Research phases are enforced obligations, not advisory labels

For every active consequential Slot, the coordinator SHALL persist the required phase set and SHALL reject delivery/readiness progression when the required deep-dive, adversarial, or validation phase is absent, unverified, or satisfied only by the same worker's assertion. A host may project phases differently, but it cannot omit their canonical obligations.

#### Scenario: Caller adds only a landscape task

- **WHEN** all manually added landscape tasks are verified but a consequential Slot has no adversarial or validation result
- **THEN** the coordinator refuses delivery preparation and emits the missing phase actions

#### Scenario: Adversarial search finds no counterevidence

- **WHEN** an independent adversarial action searches the registered methods and finds no disconfirming material
- **THEN** the negative result is persisted with method boundaries and can satisfy the adversarial attempt requirement without being treated as positive support

### Requirement: Autonomous research continues after confirmed handoff
The system SHALL replan research, retry tools, search external documentation, and switch methods without routine human collaboration while remaining inside the confirmed authority and safety boundary.

#### Scenario: A worker does not know how to use a required tool
- **WHEN** current knowledge is insufficient but public documentation or an alternate method is available
- **THEN** the system creates and executes a bounded learning or method-switch action before reporting a blocker

### Requirement: Policy scoring and pruning are reproducible

The policy SHALL use the registered six-component realized-delta vector, versioned weights, method-fit value, criticality, depth penalty, duplicate penalty, stagnation penalty, gain-ratio epsilon, pruning confidence rule, boosting failure factor, and deterministic seed. It SHALL persist all inputs and intermediate components for every selection.

#### Scenario: Same state is evaluated twice

- **WHEN** the ledger digest, policy version, configuration, and seed are unchanged
- **THEN** selected and rejected action ids, scores, tie-break order, and prune dispositions are identical

#### Scenario: Calibration changes a weight

- **WHEN** a calibration run proposes a new weight or threshold
- **THEN** it creates a versioned policy registry entry and cannot mutate historical decisions or silently alter an active run
