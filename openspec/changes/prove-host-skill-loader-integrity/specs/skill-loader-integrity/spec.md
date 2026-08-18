## ADDED Requirements

### Requirement: Every supported host records activated skill bytes

Codex, Claude, and Hermes session hooks SHALL record a sanitized skill-load
receipt for the installed `research-tree/SKILL.md`. The receipt SHALL include
schema version, session identity, byte count, line count, package and skill
SHA-256 digests, host identity, evidence state, and timestamp. It SHALL not
include prompts, provider payloads, or credentials.

#### Scenario: Start hook sees an intact installed package

- **WHEN** a supported host emits its session-start event for a project run
- **THEN** one skill-load event binds the session to the exact installed
  `SKILL.md` bytes

### Requirement: Static and host activation status are distinct for every host

Each host adapter SHALL report static package compatibility separately from
loader-integrity verification. Missing or mismatched receipt evidence SHALL be
reported as `unverified_loader_integrity` or `invalid_loader_receipt` and SHALL
NOT be represented as verified host activation.

#### Scenario: Validation has no session receipt

- **WHEN** an operator validates a structurally valid package without a receipt
- **THEN** static compatibility may pass and loader integrity is unverified

### Requirement: Host-message verification detects full-content drift

Each available host conformance probe SHALL compare host-built skill content
with the installed file and SHALL reject start, middle, or tail mutation before
the result is recorded as verified. Unavailable hosts SHALL be explicit rather
than passing.

#### Scenario: Tail instruction is absent from the loaded body

- **WHEN** the installed skill differs in its final sentinel region
- **THEN** the conformance probe reports a digest mismatch and does not issue a
  verified loader-integrity result
