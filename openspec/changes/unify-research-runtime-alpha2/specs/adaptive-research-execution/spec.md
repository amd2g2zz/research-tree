## ADDED Requirements

### Requirement: Research actions target explicit Decision Slot deficits
The system SHALL generate bounded landscape, deep-dive, adversarial, validation, or method-switch actions from an open Decision Slot, its evidence deficit, closure oracle, dependencies, and prior outcomes.

Every typed action proposal SHALL include a stable action id, run and Slot lineage,
trigger references, missing evidence classes, a method boundary, a closure oracle,
mandatory disposition, policy version/seed, and the six score components. A proposal
without a trigger reference or a closure deficit SHALL be rejected as unbounded.

#### Scenario: A broad Decision Slot has no evidence map
- **WHEN** a Decision Slot has no verified Finding Packs
- **THEN** the policy proposes a landscape action with required evidence classes and a completion oracle

#### Scenario: Evidence conflicts on a consequential option
- **WHEN** an Insight Digest marks a Slot contested
- **THEN** the policy prioritizes an adversarial or independent-method action before decision convergence

#### Scenario: A canonical deficit becomes a typed action
- **WHEN** a canonical Decision Slot deficit has a trigger, missing evidence, and closure oracle
- **THEN** the policy emits one reproducible typed action carrying those fields and the Slot priority

### Requirement: Research growth is triggered by verified state change
The system SHALL grow depth, breadth, correction, validation, or method-switch successors only from a referenced finding, failed oracle, newly exposed uncertainty, competing hypothesis, invalidated premise, or unavailable method.

#### Scenario: Finding exposes a narrower unresolved question
- **WHEN** a verified Finding Pack identifies a decision-relevant uncertainty and closure oracle
- **THEN** the policy creates a child action linked to the triggering finding and missing evidence

#### Scenario: Worker returns generic suggestions without evidence
- **WHEN** a worker proposes additional topics without a triggering evidence reference or closure deficit
- **THEN** the policy rejects those proposals as unbounded growth

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

#### Scenario: A prior oracle failed
- **WHEN** an optional action is associated with a failed closure oracle
- **THEN** the policy records a positive recovery boost and keeps the action eligible for method recovery

### Requirement: Research stops only at explicit batch, Slot, and run boundaries
The system SHALL distinguish batch checkpoint, Decision Slot closure, and run completion and SHALL NOT treat an empty static task list, worker return, completed wave, or report existence as a successful stop.

The recursive-search projection MAY rank frontier work and expose provisional
Slot/report statuses, but it SHALL label them projection-only. It SHALL NOT be the
canonical authority for Slot closure, report registration, delivery readiness, or
run completion; those decisions belong to the canonical runtime coordinator.

#### Scenario: Current frontier drains with an unclosed Slot
- **WHEN** no action is currently executable but closure obligations remain
- **THEN** the coordinator records a blocker, method switch, deferred fallback, or authority boundary rather than completion

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
