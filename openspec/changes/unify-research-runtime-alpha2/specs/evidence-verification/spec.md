## ADDED Requirements

### Requirement: Every consequential observation references resolvable evidence
The system SHALL require each consequential Finding Pack observation to reference an immutable Evidence Artifact revision and an exact selector appropriate to its medium.

#### Scenario: Repository observation is submitted
- **WHEN** an observation claims behavior in supplied source code
- **THEN** its anchor identifies the inspected repository revision, path, symbol or line selector, applicability, confidence, and limitation

#### Scenario: Document or image observation is submitted
- **WHEN** an observation is derived from a document page or image region
- **THEN** its anchor resolves to the exact content digest and page, section, or region selector used for extraction

#### Scenario: Evidence reference does not exist
- **WHEN** a Finding Pack names an unresolved or out-of-scope evidence reference
- **THEN** ingestion fails and the observation cannot affect decision state

The alpha2 runtime accepts the legacy `{kind, ref}` anchor for migration compatibility,
but a strict alpha2 evidence anchor is only accepted when the caller supplies exactly one
matching Evidence Artifact with the same content digest and revision. The resolver also
rejects rejected, quarantined, or superseded artifacts and out-of-workspace locators.

### Requirement: Evidence independence is provenance-aware
The system SHALL group evidence by originating provenance and acquisition method so derivative URLs or repeated snapshots of the same underlying source do not satisfy independent-evidence requirements.

#### Scenario: Two articles repeat one vendor announcement
- **WHEN** two distinct URLs derive their material claim from the same vendor source
- **THEN** they count as one provenance group for triangulation

### Requirement: Validation verdicts come from executable OracleRun artifacts
The system SHALL bind each validation verdict to the current OracleSpec, attempt, inputs, method, environment, tool events, result artifacts, evaluator, verdict, and limitations, and SHALL reject worker-authored verdict strings as authoritative state.

#### Scenario: Worker submits passed with a missing evidence reference
- **WHEN** a Finding Pack contains a passed string but no resolvable OracleRun for the current attempt
- **THEN** validation remains pending and the Finding Pack cannot close the Decision Slot

The alpha2 contract path uses `OracleSpec.from_mapping` and `OracleRun.from_mapping`
to retain exact execution permissions, limits, attempts, input and toolchain digests,
timeout state, result artifacts, evaluator, limitations, and reproducibility. The
legacy `create` API remains a compatibility constructor and does not itself authorize
alpha2 closure.

#### Scenario: Oracle execution fails
- **WHEN** the recorded oracle result is failed or inconclusive
- **THEN** the result remains visible and triggers an independent validation, method switch, fallback, or bounded residual-risk decision

### Requirement: Decision Slot closure is an auditable assessment
The system SHALL issue a closure token only after evaluating required evidence classes, provenance independence, counterevidence search, contradictions, oracle outcomes, selected or conditional decision status, fallback, and reversal condition.

#### Scenario: Active contradiction remains on a P0 option
- **WHEN** supported Finding Packs both support and contradict a consequential option without adjudication
- **THEN** the SlotClosureAssessment blocks selected closure and requests adversarial resolution

#### Scenario: P0 evidence and oracle requirements pass
- **WHEN** all required evidence, counterevidence, contradiction, validation, and fallback obligations resolve for the current revisions
- **THEN** the core evaluator emits a closure token that records every input reference and check result

`SlotClosureAssessment.assess_alpha2` is the evaluator-owned path. It requires
counterevidence completion, two provenance groups, every declared evidence class,
a reproducible passing OracleRun, disposed contradictions, fallback, and reversal
condition. Worker prose and legacy validation strings are not accepted inputs.

### Requirement: Evidence history is never deleted by pruning or supersession
The system SHALL preserve rejected, contradicted, superseded, failed, and inconclusive evidence with its original provenance and disposition.

#### Scenario: A premise is disproved by later evidence
- **WHEN** later evidence invalidates an earlier premise
- **THEN** the earlier artifact remains addressable and is linked to the superseding finding and revised decision

### Requirement: Oracle execution has a reproducible boundary

Every OracleSpec SHALL declare input schema, invocation adapter, allowed commands and network, resource limits, timeout, expected result schema, retry policy, and flaky-result policy. Every OracleRun SHALL record input digests, environment and toolchain digests, exit code, timeout flag, result artifacts, verdict, evaluator, and reproducibility status.

#### Scenario: Oracle times out

- **WHEN** execution exceeds its declared timeout
- **THEN** OracleRun is inconclusive or blocked with timed_out=true and a retry or method-switch action
- **AND** the timeout cannot satisfy a closure requirement

#### Scenario: Oracle is flaky

- **WHEN** repeated identical inputs produce conflicting verdicts
- **THEN** reproducibility_status is flaky, the conflict is retained, and the Slot remains open until an explicit risk-tier rule resolves it

### Requirement: Closure tokens have lifecycle and revocation semantics

A SlotClosureAssessment SHALL include required-evidence results, independence groups, counterevidence search, contradiction disposition, oracle refs and verdicts, fallback, reversal condition, assessor version, issued_at, expires_at when applicable, and a token digest. A closure token SHALL be revoked or marked stale when any parent evidence, InsightDigest, OracleRun, or Decision Ledger revision is superseded.

#### Scenario: Evidence is later invalidated

- **WHEN** a parent artifact digest or oracle result is marked stale
- **THEN** the closure token cannot be reused for readiness or delivery and the coordinator opens a traceable revalidation action
