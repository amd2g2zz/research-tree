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

`FindingPackCompiler` uses strict evidence by default: every observation must supply exactly
one matching, persisted Evidence Artifact with the same run, id, revision, content digest,
and selector, and that exact Evidence Artifact revision is appended to the Finding Pack's
parent lineage. Legacy `{kind, ref}` anchors are available only through the explicit
`allow_legacy_evidence` migration switch. The resolver also rejects changed repository
revisions, locator path mismatches, rejected/quarantined/superseded artifacts, and
out-of-workspace locators.

### Requirement: Evidence independence is provenance-aware
The system SHALL group evidence by originating provenance and acquisition method so derivative URLs or repeated snapshots of the same underlying source do not satisfy independent-evidence requirements.

Canonical Evidence Artifacts carry both `provenance_origin` and the deterministic
`provenance_group_for(origin, acquisition_method)` result. Ingestion rejects a caller-supplied
group that does not match that computation.

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
OracleSpec version, execution method, tool-event references, timeout state, result
artifacts, evaluator, limitations, and reproducibility. The
legacy `create` API remains a compatibility constructor and does not itself authorize
alpha2 closure.

The coordinator rejects direct `p0_closure` obligation writes unless the evidence
reference resolves to a persisted passed assessment token. A worker-authored status,
arbitrary string, report field, or host event cannot satisfy this obligation.

Finding Packs persist only exact `oracle_run_refs` containing the OracleRun id,
OracleAttempt id, OracleSpec id and version, and action attempt id. Supplying the alpha1
`validation_result` field fails compilation. The adaptive policy resolves every ref
against coordinator-provided OracleRun data before applying failure reweighting.

Every `OracleRun.result_artifact_refs` entry is an exact artifact reference with
`run_id`, `artifact_id`, positive `revision`, and `content_hash`. The coordinator
accepts only references that resolve to the current run and whose persisted digest
matches exactly. A path, bare artifact id, cross-run ref, missing revision, or stale
digest cannot enter the OracleRun ledger.

The coordinator persists an immutable OracleSpec revision before execution. Each
OracleAttempt has its own id and binds one current action attempt to that exact
OracleSpec payload digest, method, input digests, environment digest, toolchain
digest, and UTC start time. OracleRun carries both `oracle_attempt_id` and the
action `attempt_id`; all shared execution-boundary fields must equal the persisted
OracleAttempt before any verdict or result artifact is accepted.

#### Scenario: Oracle execution binding is forged or stale
- **WHEN** an OracleRun names an absent OracleAttempt or changes its action attempt, OracleSpec revision, method, input, environment, or toolchain binding
- **THEN** the coordinator rejects the OracleRun without advancing the run revision

#### Scenario: Oracle execution fails
- **WHEN** the recorded oracle result is failed or inconclusive
- **THEN** the result remains visible and triggers an independent validation, method switch, fallback, or bounded residual-risk decision

#### Scenario: Oracle result artifact cannot be replayed
- **WHEN** an OracleRun references a missing, cross-run, or digest-mismatched result artifact
- **THEN** the coordinator rejects the OracleRun without advancing the run revision

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
condition. The token also binds the exact Decision Ledger artifact revision and
its selected or conditional status. Worker prose and legacy validation strings
are not accepted inputs.

The coordinator SHALL bind closure to the active P0 Slot set from one exact
Blueprint Target revision. It SHALL verify that each assessment Slot id equals the
referenced Decision Ledger entry's Slot id and that the decision belongs to the
bound Blueprint Target. It SHALL persist a deterministic `P0ClosureAggregate` over
the latest assessment for every active P0 Slot. A Slot token is not a run-level
closure token and MUST NOT directly satisfy the `p0_closure` obligation.

#### Scenario: Only one of two P0 Slots passes
- **WHEN** the active Blueprint Target has two P0 Slots and only one has a current passed assessment
- **THEN** the aggregate remains open, identifies the missing Slot, and the run-level P0 obligation remains unsatisfied

#### Scenario: Every active P0 Slot passes
- **WHEN** every active P0 Slot has a current passed assessment bound to its exact Decision Ledger revision
- **THEN** the core evaluator persists a passed aggregate and uses its digest as the run-level P0 closure evidence

#### Scenario: Assessment names a different Slot
- **WHEN** an assessment Slot id differs from the referenced Decision Ledger entry's Slot id
- **THEN** ingestion fails without advancing the run revision

#### Scenario: Blueprint Target is superseded
- **WHEN** a newer exact Blueprint Target revision changes the active P0 Slot set
- **THEN** the prior aggregate cannot satisfy completion and the new aggregate reports every newly open or changed Slot

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

#### Scenario: Failed or inconclusive OracleRun creates successor work
- **WHEN** a failed or inconclusive OracleRun is recorded for an open Decision Slot
- **THEN** the scheduler persists a distinct canonical WorkItem referencing the exact OracleRun, OracleAttempt, and OracleSpec revision
- **AND** a failed result selects a method-switch action while an inconclusive result selects independent validation
- **AND** replaying the scheduling request is idempotent and does not create a second WorkItem or advance the run revision

### Requirement: Closure tokens have lifecycle and revocation semantics

A SlotClosureAssessment SHALL include required-evidence results, independence groups, counterevidence search, contradiction disposition, oracle refs and verdicts, fallback, reversal condition, assessor version, issued_at, expires_at when applicable, and a token digest. A closure token SHALL be revoked or marked stale when any parent evidence, InsightDigest, OracleRun, or Decision Ledger revision is superseded.

#### Scenario: Evidence is later invalidated

- **WHEN** a parent artifact digest or oracle result is marked stale
- **THEN** the closure token cannot be reused for readiness or delivery and the coordinator opens a traceable revalidation action

Material or terminal FeedbackEvents append a successor `revoked` assessment revision,
preserve the prior passed assessment and token for replay, clear the canonical P0
closure obligation, and include the revoked token in the feedback event.
