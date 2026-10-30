## ADDED Requirements

### Requirement: data-source providers plug in behind one port

Retrieval providers implement `DataSourceProvider` (capabilities/search/fetch)
and register by name; the engine selects via a config-driven default.

#### Scenario: registry resolves the default provider
- **WHEN** anysearch is registered and set as default
- **THEN** `registry.default()` returns it; unknown names raise a registry error

#### Scenario: manifests are listed without usage bodies
- **WHEN** N providers are registered
- **THEN** `manifests()` returns N lightweight manifests (name/capabilities/kinds/description/usage pointer) and no credential or usage content

### Requirement: retrieval actions are audited as events

Every search/fetch through the audit decorator emits one `provider.action`
event; failures record outcome "error" without leaking internals.

#### Scenario: search emits provider identity and result count
- **WHEN** an audited provider search returns 1 result
- **THEN** the event stream holds a `provider.action` event with provider name, target, outcome "ok", and result_count 1

#### Scenario: fetch emits byte metrics
- **WHEN** an audited provider fetch returns a document
- **THEN** the event carries the target url and the byte count

#### Scenario: failures are recorded and re-enveloped
- **WHEN** the inner provider throws
- **THEN** the audit event records outcome "error" without the internal error text, and the caller receives a `ProviderActionError`

### Requirement: credentials never enter the audit trail

Provider config is injected at construction; the audit decorator serializes
only manifest and call data.

#### Scenario: api keys stay out of events
- **WHEN** a provider is constructed with a config containing an api key and performs searches
- **THEN** no event in the stream contains the key

### Requirement: anysearch is the default search adapter

The anysearch adapter wraps the anysearch CLI (json output) with an injectable
runner; fetch is unsupported by contract.

#### Scenario: search maps CLI output
- **WHEN** the runner returns a JSON array of {title,url,snippet}
- **THEN** search returns the mapped results

#### Scenario: structured failure
- **WHEN** the CLI exits non-zero
- **THEN** search raises a structured anysearch failure (not a raw spawn error)
