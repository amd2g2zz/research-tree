## MODIFIED Requirements

### Requirement: InsightDigest is a first-class versioned artifact

The runtime SHALL persist and validate a complete current InsightDigest with
schema and producer versions, digest identity, exact source and Decision Slot
references, classified statements, evidence classes, confirmed facts,
hypotheses, contradictions, unresolved gaps, recommendations, limitations,
confidence/calibration, changed beliefs, previous digest and parent
references, realized delta, evidence baseline, transition index, policy
signals, next actions, closure disposition, and Finding Pack count. It SHALL
reject every payload that omits a required current field or carries an
unsupported schema version before policy, scheduler, replay, or delivery
consumption. It SHALL NOT parse, normalize, project, migrate, or otherwise
support a prior minimal digest shape.

#### Scenario: Findings are synthesized

- **WHEN** a new verified Finding Pack batch is ingested
- **THEN** the digest is recomputed from canonical inputs with every current
  required field and the prior digest remains immutable

#### Scenario: Prior digest shape is supplied

- **WHEN** a caller supplies an unversioned or incomplete prior digest
- **THEN** validation rejects it before it can affect a current runtime
  boundary
