## ADDED Requirements

### Requirement: Research methods and tools are registered

The runtime SHALL maintain a method/tool registry describing capability, input media, permissions, invocation adapter, output schema, timeout, retryability, provenance behavior, and known limitations for repository inspection, web/search, documents, images, experiments, and code execution.

The minimum fallback order for an unresolved question SHALL be local context inspection, registered documentation or repository search, a distinct extraction or execution method, independent validation, and only then a persisted blocker or authority request. Each method switch SHALL reference the failed attempt, preserve the source and error classification, and choose a method with a different failure boundary; repeating the same failed call is not a method switch.

#### Scenario: Tool selection is made

- **WHEN** the policy selects a tool
- **THEN** the action records the registry version, selection reason, permission profile, and expected evidence class

### Requirement: Search Portfolios derive acquisition from intent and deficits

Before dispatching an acquisition batch, the system SHALL persist a SearchPortfolio derived from the confirmed IntentModel revision, WorkingBrief revision, active Decision Slot, current evidence deficit, and prior acquisition outcomes. It SHALL contain explicit and implicit subquestions, query rewrites, source classes, method/provider identities, expected contribution, failure boundaries, and batch reassessment criteria.

#### Scenario: The requester names a broad topic

- **WHEN** the confirmed intent leaves consequential mechanisms, implementation constraints, failure modes, or validation questions implicit
- **THEN** the portfolio adds traceable subquestions and query rewrites for those deficits without changing requester-controlled outcome or authority

#### Scenario: The same provider receives several rewritten queries

- **WHEN** several calls use one search index, provider, or mirrored corpus
- **THEN** they remain one method/provider boundary and do not satisfy an independent-method requirement by query count alone

### Requirement: Acquisition uses independent method boundaries when decisions require them

The system SHALL distinguish query, provider, corpus, extraction method, repository inspection, primary-source retrieval, and experiment identities. A portfolio requiring independent coverage SHALL select methods with materially distinct provenance or failure boundaries and SHALL record when only one boundary is available.

#### Scenario: General search results repeat the same secondary claim

- **WHEN** multiple pages derive from one announcement or index result
- **THEN** the system groups them as dependent provenance and schedules a primary source, repository inspection, or experiment where required

### Requirement: Every acquisition batch receives a depth disposition

After each acquisition batch, the coordinator SHALL assess subquestion coverage, evidence classes, provenance independence, source depth, contradictions, implementation uncertainty, and oracle readiness and SHALL persist one of `deepen`, `broaden`, `pivot`, `validate`, or `sufficient_for_slot` with causal refs.

#### Scenario: Search snippets are relevant but insufficient

- **WHEN** the first batch identifies relevant sources without resolving a material Decision Slot
- **THEN** the next action opens the full source, inspects code/data, or runs a bounded experiment instead of compiling a report

### Requirement: External sources are snapshotted and provenance-linked

Every external retrieval SHALL produce an immutable SourceCapture and AcquisitionReceipt recording locator, retrieval time, response digest, media type, license/access note, extractor version, selector, fetch status, and failure history. Derivative sources SHALL link to their origin group. A successful receipt may be committed only after the captured bytes or registered immutable locator are durable.

#### Scenario: URL changes between attempts

- **WHEN** a later retrieval has a different digest
- **THEN** it becomes a new artifact revision and cannot silently replace the earlier evidence

#### Scenario: Retrieval succeeds and the worker crashes during analysis

- **WHEN** source bytes were committed before a Finding Pack was submitted
- **THEN** the successor attempt can resolve the SourceCapture and receipt without repeating the retrieval

### Requirement: Acquisition failure produces a next method

Search no-result, blocked URL, parser error, unsupported media, rate limit, and unavailable tool outcomes SHALL have typed failure codes and a registered alternate method or explicit authority escalation.

#### Scenario: Search backend is unavailable

- **WHEN** the primary search provider fails
- **THEN** the agent records the failure and tries an allowed alternate provider, local reference, repository source, or experiment before declaring a blocker

### Requirement: Multimodal selectors are exact

Document, image, and source selectors SHALL identify an immutable digest plus page/section, region coordinates, line/symbol, or fragment hash, and SHALL record extraction confidence and limitations.

#### Scenario: Image region is re-rendered

- **WHEN** the underlying image digest changes
- **THEN** the old anchor no longer validates against the new image and dependent claims are reopened or marked stale
