## ADDED Requirements

### Requirement: Public cases remain isolated from hidden oracle material
The evaluator SHALL accept only versioned public inputs and opaque oracle references in worker-visible case manifests, and MUST reject expected answers, patches, private prompts, secrets, or hidden oracle bodies.

#### Scenario: Public case contains hidden material
- **WHEN** a public case includes an expected patch or hidden oracle body
- **THEN** manifest validation fails before any release metric is computed

### Requirement: Release integrity gates are non-negotiable
The evaluator SHALL require zero false completion, complete P0 evidence and closure resolution, recovery preservation, semantic delivery consistency, and required-host canonical parity before returning a passing release decision.

#### Scenario: Quality is high but false completion exists
- **WHEN** semantic quality diagnostics exceed thresholds but any adversarial case falsely completes
- **THEN** the release decision fails with the false-completion gate identified

### Requirement: Host execution limitations are honest
The manifest SHALL record each required host execution as passed, failed, or unavailable with canonical artifact references and limitations, and MUST NOT interpret unavailable execution as parity success.

#### Scenario: Hermes execution is unavailable
- **WHEN** the manifest lacks a live Hermes result and records a capability limitation
- **THEN** the evaluator retains the diagnostic but fails the required-host parity gate

### Requirement: Independent implementation and blinded review remain separate evidence
The evaluator SHALL retain independent implementation results and blinded expert reviews as evaluator-owned evidence with declared limitations, and SHALL reject self-review or an uncalibrated LLM score as the sole quality authority.

#### Scenario: Sole evaluator is the producing worker
- **WHEN** a result identifies the producing worker as its only evaluator
- **THEN** the independent-evidence gate fails

### Requirement: Release evidence is offline-verifiable
The release decision SHALL bind the implementation revision, case/version, command, environment digest, host/package identity, artifact references, opaque oracle verdict digest, evaluator identity, review references, and limitations.

#### Scenario: Retained result omits environment binding
- **WHEN** a result lacks an environment digest or source revision
- **THEN** the manifest is invalid and no release decision is emitted

### Requirement: Semantic diagnostics cannot waive integrity failures
The evaluator SHALL report intent fidelity, unsupported claims, contradiction handling, depth, implementation success, rediscovery burden, and professional usefulness separately from hard gates.

#### Scenario: Weighted average would hide a failed oracle
- **WHEN** aggregate quality is high but an oracle or P0 evidence reference is unresolved
- **THEN** the evaluator reports the quality observations and still returns a failed decision

## MODIFIED Requirements

### Requirement: Research quality is measured by decision impact
The system SHALL evaluate research quality by intent fidelity, evidence quality, provenance independence, unsupported claims, contradiction handling, Decision Slot coverage, oracle reproducibility, recovery, implementation success, rediscovery burden, host parity, and requester acceptance rather than by source count, waves, headings, report length, or self-reported completion.

#### Scenario: Superficial metric improves without decision evidence
- **WHEN** a candidate increases source, URL, wave, heading, or byte counts without resolving current Decision Slot obligations
- **THEN** the release evaluator records no integrity improvement and MUST NOT pass the candidate from those proxy changes
