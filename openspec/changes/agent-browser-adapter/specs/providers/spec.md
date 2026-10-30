## ADDED Requirements

### Requirement: agent-browser fetches rendered-web pages as agent-readable documents

The adapter implements the DataSourceProvider port with fetch-only
capabilities (kinds: web-rendered) over the agent-browser CLI.

#### Scenario: JS-rendered page extracts to text
- **WHEN** `read <url>` returns non-empty agent-readable text
- **THEN** fetch returns a document with that text, contentType text/markdown, and utf8 byte count

#### Scenario: interaction-gated page falls back to open + snapshot
- **WHEN** `read` returns empty output
- **THEN** the adapter opens the page and takes an accessibility snapshot, returning its content

### Requirement: failures are structured, never silent empty evidence

#### Scenario: CLI failure raises before a document exists
- **WHEN** any CLI step exits non-zero
- **THEN** fetch raises a structured agent-browser failure

#### Scenario: empty extraction raises
- **WHEN** extraction yields whitespace-only output
- **THEN** fetch raises naming the empty extraction (bot wall or empty page)
