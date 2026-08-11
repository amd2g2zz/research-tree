## MODIFIED Requirements

### Requirement: Policy scoring and pruning are reproducible

The policy SHALL use a registered six-component realized-delta vector,
versioned weights, method-fit value, criticality, depth penalty, duplicate
penalty, stagnation penalty, gain-ratio epsilon, pruning confidence rule,
boosting failure factor, canonical input digest, and deterministic seed. It
SHALL return all normalized inputs and intermediate components in an immutable
selection trace. Only the coordinator may persist or accept a selected proposal.
Optional duplicate, dominated, superseded, or decision-neutral actions SHALL be
deferred with retained causal lineage. Mandatory P0 counterevidence,
contradictions, and required validation SHALL not be removed by score or
capacity pruning.

#### Scenario: Same state is evaluated twice

- **WHEN** the ledger digest, policy version, configuration, and seed are
  unchanged
- **THEN** selected and rejected action ids, scores, tie-break order, and prune
  dispositions are identical

#### Scenario: Calibration changes a weight

- **WHEN** a calibration run proposes a new weight or threshold
- **THEN** it creates a versioned policy registry entry and cannot mutate
  historical decisions or silently alter an active run

#### Scenario: Optional branch is dominated

- **WHEN** an optional action duplicates the Slot, normalized question, method,
  and oracle of a higher-value proposal
- **THEN** it is deferred with a reference to the retained action and its
  evidence lineage remains available
