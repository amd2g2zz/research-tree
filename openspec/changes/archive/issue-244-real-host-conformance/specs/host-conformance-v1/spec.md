## ADDED Requirements

### Requirement: Conformance case is deterministic with negative oracles
The frozen case SHALL declare two independent leaves, one contradiction, one validation phase, and expected canonical events, and MUST include negative oracles under which projected identities, synthetic Finding Packs, and capability strings fail.

#### Scenario: Synthetic completion is rejected
- **WHEN** a mode run supplies a projected worker identity or synthetic Finding Pack
- **THEN** the harness records a conformance failure for that cell

### Requirement: Claimed modes produce equivalent canonical semantics
Each claimed-available mode MUST run from a fresh project root through a real host process and yield the expected canonical event sequence, identity binding, Finding Pack admission, contradiction replanning, and completion gating. Unavailable modes MUST record blockers.

#### Scenario: Mode converges on the expected sequence
- **WHEN** a claimed mode completes the frozen case normally
- **THEN** its canonical event kinds, attempt identities, and gating match the expected sequence modulo host-native metadata

#### Scenario: Fault injection never false-completes
- **WHEN** a fault (kill, cancellation, stale child, modified artifact) is injected
- **THEN** the affected attempts resolve unknown/failed/blocked and no completion is recorded for them

### Requirement: Replay matches persisted state
A separate-process replay over persisted artifacts MUST reproduce the accepted canonical state, unresolved work, attempt IDs, and causal sequence exactly.

#### Scenario: Replay divergence fails the gate
- **WHEN** replay state differs from the recorded run state
- **THEN** the mode result is failed with the divergence enumerated

### Requirement: Prior synthetic attempts are superseded explicitly
The tracked comparison table SHALL map every prior synthetic/pilot cross-host attempt to its non-acceptance reason and the new source-bound receipt that supersedes it.

#### Scenario: No silent promotion
- **WHEN** the table is emitted
- **THEN** each prior pilot appears with its reason and superseding receipt path
