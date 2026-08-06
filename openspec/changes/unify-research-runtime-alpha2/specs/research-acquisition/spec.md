## ADDED Requirements

### Requirement: Research methods and tools are registered

The runtime SHALL maintain a method/tool registry describing capability, input media, permissions, invocation adapter, output schema, timeout, retryability, provenance behavior, and known limitations for repository inspection, web/search, documents, images, experiments, and code execution.

The minimum fallback order for an unresolved question SHALL be local context inspection, registered documentation or repository search, a distinct extraction or execution method, independent validation, and only then a persisted blocker or authority request. Each method switch SHALL reference the failed attempt, preserve the source and error classification, and choose a method with a different failure boundary; repeating the same failed call is not a method switch.

#### Scenario: Tool selection is made

- **WHEN** the policy selects a tool
- **THEN** the action records the registry version, selection reason, permission profile, and expected evidence class

### Requirement: External sources are snapshotted and provenance-linked

Every external retrieval SHALL record locator, retrieval time, response digest, media type, license/access note, extractor version, selector, and fetch failure history. Derivative sources SHALL link to their origin group.

#### Scenario: URL changes between attempts

- **WHEN** a later retrieval has a different digest
- **THEN** it becomes a new artifact revision and cannot silently replace the earlier evidence

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
