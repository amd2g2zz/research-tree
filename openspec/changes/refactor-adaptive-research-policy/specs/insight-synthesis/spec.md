## MODIFIED Requirements

### Requirement: InsightDigest is a first-class versioned artifact

The runtime SHALL persist or validate an InsightDigest with schema version,
producer version, exact source and Decision Slot references, classified
statements, covered evidence classes, confirmed facts, hypotheses,
contradictions, unresolved gaps, confidence/calibration, changed beliefs,
recommended actions, limitations, previous digest reference, and exact parent
references. It SHALL expose uncovered, thin, contested, qualified, and
converging signals as policy inputs. A digest SHALL not issue a closure token or
mark lifecycle completion.

#### Scenario: Findings are synthesized

- **WHEN** a new verified Finding Pack batch is ingested
- **THEN** the digest is deterministically recomputed from sorted canonical
  inputs, retains exact lineage, and leaves the prior digest immutable

#### Scenario: Digest has malformed lineage

- **WHEN** a digest references a missing, duplicate, or wrong-slot source
- **THEN** validation rejects the digest before it can be used for policy input

### Requirement: Insight changes trigger bounded research actions

Growth SHALL be triggered only by a newly exposed gap, contradiction, invalid
premise, failed oracle, method limitation, or material implementation
uncertainty represented in the digest. A duplicate batch with no
closure-relevant change SHALL record zero delta and a no-progress penalty;
the digest itself SHALL not persist an action or mutate run state.

#### Scenario: Digest has no closure-relevant change

- **WHEN** a new batch adds only duplicate provenance and no changed uncertainty
- **THEN** the digest records zero realized change and returns no unbounded
  growth trigger
