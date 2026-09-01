# Stable Lifecycle CLI

## Requirement: supported public lifecycle

The product SHALL advertise exactly the `install`, `doctor`, `run`, `resume`,
`status`, and `verify` lifecycle commands through the `research-tree` console
entrypoint.

### Scenario: caller creates a governed run without internal schema knowledge

- **WHEN** a caller invokes `research-tree run` with a workspace, host,
  project/run identifiers, and plain-language outcome, scope, authority, and
  success oracle
- **THEN** the command creates a canonical durable request and returns schema
  version 1 with the canonical authority revision
- **AND THEN** the response contains explicit readiness failures rather than a
  completion decision.

## Requirement: fail-closed verification

The product SHALL not let lifecycle status or verification authorize completion
without canonical authority, oracle evidence, and an independent reviewer
receipt.

### Scenario: initial verification

- **WHEN** a newly prepared lifecycle run is verified
- **THEN** the command returns `verification_pending` with the missing evidence
- **AND THEN** it exits nonzero and identifies human plus canonical coordinator
  completion authority.

## Requirement: internal transport isolation

Raw HostEvent and SQLite coordinator operations SHALL not appear in public help.

### Scenario: public help

- **WHEN** a caller runs `research-tree --help`
- **THEN** HostEvent ingestion and coordinator completion verbs are absent
- **AND THEN** maintainer-only transport requires explicit acknowledgement under
  the internal command boundary.
