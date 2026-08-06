## ADDED Requirements

### Requirement: Evaluation manifests are complete and frozen before execution

An evaluation manifest SHALL contain schema version, corpus/case ids, alpha1 and prompt-baseline revisions, alpha2 source/package revisions, host/version matrix, environment digests, commands, random seeds, network-recording policy, oracle interfaces, metrics, aggregation, missing-data handling, expert rubric, thresholds, and release gates.

#### Scenario: Candidate changes the threshold after seeing results

- **WHEN** a release candidate modifies a manifest field after any scored run
- **THEN** the manifest digest changes and the prior results cannot be used for the new gate

### Requirement: Quality metrics have executable definitions

The evaluator SHALL define numerator, denominator, unit, aggregation, unavailable-data behavior, and evidence path for at least intent_fidelity, premature_handoff, unsupported_claim, false_completion, p0_closure, recovery_loss, host_parity, implementation_success, rediscovery_burden, and human_acceptance.

The initial frozen definitions SHALL be: `intent_fidelity = accepted material intent fields / material intent fields`; `premature_handoff = handoffs before the readiness predicate / eligible runs`; `unsupported_claim = consequential claims without a resolvable evidence or oracle reference / consequential claims`; `false_completion = runs entering completed while any hard gate is false / eligible runs`; `p0_closure = P0 Slots with a valid current closure token / active P0 Slots`; `recovery_loss = obligations absent after replay / obligations before crash`; `host_parity = semantically equal canonical digests / equivalent host traces`; `implementation_success = independent runners satisfying the declared task oracle / implementation cases`; `rediscovery_burden = repeated acquisition actions for an already-covered provenance group / acquisition actions`; and `human_acceptance = accepted exact delivery pairs / submitted exact delivery pairs`. Each metric SHALL publish its case-level numerator, denominator, unavailable reason, and artifact path. `false_completion` has an absolute threshold of zero; all other thresholds are versioned in the pre-run manifest.

#### Scenario: A case cannot exercise one dimension

- **WHEN** a metric is not applicable to a case
- **THEN** the evaluator records not_applicable with a reason and excludes it from the denominator rather than treating it as a pass

### Requirement: Absolute safety gates override aggregate quality

Release SHALL fail if false completion is nonzero, any required P0 evidence or closure reference is unresolved, recovery loses an obligation, a hidden oracle is leaked, or semantically equivalent hosts diverge, regardless of prose or aggregate score.

#### Scenario: Aggregate score improves while false completion occurs

- **WHEN** alpha2 scores higher overall but one adversarial fixture falsely completes
- **THEN** the release is rejected and the failure is linked to the exact trace and state transition

### Requirement: Independent implementation and blinded review are reproducible

Each comparison run SHALL provide only allowed public inputs to an isolated implementation runner and SHALL retain reviewer rubric version, reviewer role, blinded assignment, raw score components, disagreements, adjudication, and limitations.

#### Scenario: Expert score conflicts with automated gate

- **WHEN** blinded review finds shallow reasoning despite structural checks passing
- **THEN** the semantic failure remains visible and requires adjudication or additional evidence before release

### Requirement: Release evidence is exportable without rerunning

The release exporter SHALL produce an immutable manifest/index that resolves every claim to case, command, environment, artifact, oracle, trace, comparison, and limitation, with a verification command and exit code.

#### Scenario: Reviewer audits a claim offline

- **WHEN** a reviewer receives the release evidence bundle without the original workspace
- **THEN** digest verification and replay metadata identify which claims are verifiable, unavailable, or unsupported
