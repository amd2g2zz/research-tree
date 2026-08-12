## ADDED Requirements

### Requirement: Portfolio derives research work from intent and deficits

The system SHALL persist a SearchPortfolio before acquisition dispatch, bound to
the exact IntentModel revision, WorkingBrief revision, strategy revision,
Decision Slot id, evidence deficit, prior acquisition refs, and authority
envelope.

#### Scenario: Consequential mechanism is implicit
- **WHEN** the confirmed intent leaves mechanism, implementation boundary,
  failure mode, validation, or requester consequence implicit
- **THEN** the portfolio records traceable subquestions and query rewrites that
  name their originating deficit and expected decision effect

### Requirement: Method boundaries are materially independent

The portfolio SHALL distinguish query variant, provider, corpus, extraction
method, repository inspection, primary-source retrieval, documentation lookup,
scholarly lookup, and experiment identities, and MUST NOT count repeated
queries through one backend as independent methods.

#### Scenario: One provider receives several query rewrites
- **WHEN** multiple rewritten queries use one search index, provider, or mirrored corpus
- **THEN** they remain one method boundary and cannot satisfy an independent-method obligation by query count alone

### Requirement: Degraded capability is explicit

The portfolio SHALL record unavailable, failed, unsupported, or permission-limited
methods with a limitation and alternate evidence class where one is available.

#### Scenario: Only one search backend exists
- **WHEN** the registry exposes only one available search provider
- **THEN** the run records degraded search capability and switches to direct source, repository, documentation, or experiment evidence where applicable

### Requirement: Batch assessment controls deepen, broaden, pivot, validate, or stop

After every acquisition batch, the system SHALL assess coverage, novelty,
provenance independence, source depth, contradictions, implementation
uncertainty, oracle readiness, and unresolved decision risk before selecting
`deepen`, `broaden`, `pivot`, `validate`, `sufficient_for_slot`, or `blocked`.

#### Scenario: First batch is relevant but shallow
- **WHEN** a batch finds relevant snippets or secondary summaries but leaves the Decision Slot materially underdetermined
- **THEN** the next action deepens through full-source reading, code/data inspection, primary-source retrieval, or bounded experiment instead of drafting delivery

### Requirement: Strategy pivots preserve lineage and authority

Evidence that invalidates the initial framing SHALL create a successor strategy
or action-graph revision with the superseded direction, reason, causal evidence,
and authority disposition.

#### Scenario: Evidence changes requester-controlled outcome
- **WHEN** new evidence requires a different requester outcome, permission, or safety boundary
- **THEN** the system reopens the human decision instead of silently expanding authority

### Requirement: Portfolio evidence resolves to captures and checkpoints

Portfolio outcomes SHALL reference immutable SourceCapture, AcquisitionReceipt,
and AnalysisCheckpoint artifacts from #80 when evidence exists, and SHALL record
typed unavailable or failed dispositions when it does not.

#### Scenario: Retrieval succeeds before a worker crash
- **WHEN** a source capture and acquisition receipt are committed before a Finding Pack
- **THEN** the successor attempt resolves those refs and continues from the checkpoint without blind reacquisition
## MODIFIED Requirements

### Requirement: Search Portfolios derive acquisition from intent and deficits

Before dispatching an acquisition batch, the system SHALL persist a
SearchPortfolio derived from the confirmed IntentModel revision, WorkingBrief
revision, active Decision Slot, current evidence deficit, prior acquisition
outcomes, and authority envelope. It SHALL contain explicit and implicit
subquestions, query rewrites, source classes, method/provider identities,
expected contribution, failure boundaries, and batch reassessment criteria.

#### Scenario: The requester names a broad topic
- **WHEN** the confirmed intent leaves consequential mechanisms, implementation constraints, failure modes, or validation questions implicit
- **THEN** the portfolio adds traceable subquestions and query rewrites for those deficits without changing requester-controlled outcome or authority

#### Scenario: The same provider receives several rewritten queries
- **WHEN** several calls use one search index, provider, or mirrored corpus
- **THEN** they remain one method/provider boundary and do not satisfy an independent-method requirement by query count alone

#### Scenario: Source capture lineage is required
- **WHEN** acquisition evidence is used to support a portfolio outcome
- **THEN** the outcome references SourceCapture, AcquisitionReceipt, and AnalysisCheckpoint refs or records an explicit unavailable disposition

### Requirement: Acquisition uses independent method boundaries when decisions require them

The system SHALL distinguish query, provider, corpus, extraction method,
repository inspection, primary-source retrieval, documentation lookup, scholarly
lookup, and experiment identities. A portfolio requiring independent coverage
SHALL select methods with materially distinct provenance or failure boundaries
and SHALL record when only one boundary is available.

#### Scenario: General search results repeat the same secondary claim
- **WHEN** multiple pages derive from one announcement or index result
- **THEN** the system groups them as dependent provenance and schedules a primary source, repository inspection, documentation lookup, or experiment where required

#### Scenario: Method boundary is degraded
- **WHEN** the required independent method is unavailable or permission-limited
- **THEN** the action records the limitation, rejected method, selected fallback, and remaining decision risk

### Requirement: Every acquisition batch receives a depth disposition

After each acquisition batch, the coordinator SHALL assess subquestion coverage,
evidence classes, provenance independence, source depth, contradictions,
implementation uncertainty, oracle readiness, and unresolved decision risk and
SHALL persist one of `deepen`, `broaden`, `pivot`, `validate`,
`sufficient_for_slot`, or `blocked` with causal refs.

#### Scenario: Search snippets are relevant but insufficient
- **WHEN** the first batch identifies relevant sources without resolving a material Decision Slot
- **THEN** the next action opens the full source, inspects code/data, retrieves the primary source, or runs a bounded experiment instead of compiling a report

#### Scenario: Evidence invalidates the starting direction
- **WHEN** acquired evidence contradicts the active strategy premise
- **THEN** the assessment records `pivot`, preserves the superseded strategy ref, and proposes a successor strategy inside the authority envelope
