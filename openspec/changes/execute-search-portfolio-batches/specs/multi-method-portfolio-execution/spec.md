## ADDED Requirements

### Requirement: Execution is bound to selected method/provider boundaries

The runtime SHALL represent each method outcome with its portfolio, batch,
method, provider, failure boundary, selection reason, and stable query
references. A query count or repeated query against one provider SHALL NOT
establish independent method/provider coverage.

#### Scenario: Two queries use one provider
- **WHEN** a batch contains multiple query references for one method/provider
  boundary
- **THEN** its provenance assessment is `single-boundary` and capability is not
  reported as independent

#### Scenario: Two independent methods are selected
- **WHEN** outcomes come from at least two distinct method and provider
  boundaries
- **THEN** the batch records `independent` provenance and preserves each
  boundary's selection reason

### Requirement: Typed failures select alternatives before blocking

The runtime SHALL accept typed `http-404`, `no-result`, `parser-failure`,
`rate-limit`, and `shallow` outcomes. When an unused available registration
exists, a failure SHALL expose a fallback method selection or direct-source,
deepen, or experiment action before a blocker is reported.

#### Scenario: A provider is rate limited
- **WHEN** a selected method returns `rate-limit` and another available
  boundary exists
- **THEN** the assessment chooses `switch` and records a fallback method

#### Scenario: No result has no alternate boundary
- **WHEN** a method returns `no-result` and no available alternate exists
- **THEN** the assessment chooses `rewrite` and does not claim captured evidence

#### Scenario: A snippet is shallow
- **WHEN** a method captures only snippet-level material
- **THEN** the assessment chooses `deepen` and requests full-source extraction

### Requirement: Every batch records bounded decision metrics

After each dependency-ready batch the runtime SHALL record coverage, novelty,
contradictions, source quality, provenance independence, and unresolved
decision risk. The assessment SHALL choose only `stop`, `rewrite`, `switch`,
`deepen`, `experiment`, `pivot`, or `blocked` (legacy names may be decoded only
as explicit compatibility values).

#### Scenario: Evidence contradicts the initial framing
- **WHEN** a batch contains a contradiction inside the confirmed authority
  envelope
- **THEN** the assessment chooses `pivot` and records superseded and successor
  strategy revisions

#### Scenario: Implementation risk remains unresolved
- **WHEN** coverage is complete but implementation or oracle readiness remains
  unresolved
- **THEN** the assessment chooses `experiment` rather than `stop`

### Requirement: Execution remains a pure non-authoritative projection

The execution and assessment values SHALL be immutable, strictly decodable,
deterministically serializable, and free of raw query text/private prompts.
They SHALL NOT persist coordinator state, alter worker-finish gating, or grant
completion authority.

#### Scenario: A caller serializes an execution result
- **WHEN** the result is encoded and decoded
- **THEN** the canonical bytes are stable and hidden prompt fields are rejected
