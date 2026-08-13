## ADDED Requirements

### Requirement: Hermes package declares executable closure
The package builder SHALL maintain one deterministic Hermes executable closure
containing every documented Python entrypoint, its transitive in-package local
Python modules, and all runtime resources required by those entrypoints.

#### Scenario: Sibling import is part of the closure
- **WHEN** a documented Hermes entrypoint imports a sibling package script
- **THEN** the builder includes that sibling script in both the checked-in
  package and every staged GitHub bundle

#### Scenario: Unknown local dependency fails closed
- **WHEN** an executable closure references a required local file that is
  absent from the package source
- **THEN** package construction and validation fail with that dependency path
  before reporting a compatible package

### Requirement: Hermes compatibility is cold-start verified
The Hermes adapter SHALL report `compatible=true` for an external directory or
GitHub bundle only after every documented executable entrypoint starts from an
unrelated working directory with an empty `PYTHONPATH` and no source checkout
on `sys.path`.

#### Scenario: Isolated documented entrypoints start
- **WHEN** a generated Hermes package is copied to a temporary standalone
  directory and each documented script is invoked with `--help`
- **THEN** each invocation exits zero without importing the repository source

#### Scenario: Missing transitive module rejects compatibility
- **WHEN** a required executable dependency is removed from a staged bundle
- **THEN** validation reports the exact missing dependency and returns
  `compatible=false`

### Requirement: Staging preserves executable bundle parity
The `stage` command SHALL copy the same validated executable closure as the
generated Hermes package and SHALL prove package/staged closure parity before
returning success.

#### Scenario: Staged provider recovery remains executable
- **WHEN** the staged execution adapter receives an isolated retryable
  provider-failure/recovery fixture
- **THEN** it produces the non-authoritative recovery events without repository
  source access

#### Scenario: Generated package parity remains reproducible
- **WHEN** package sources and the closure declaration are unchanged
- **THEN** rebuilding packages yields identical Hermes package contents and
  validation results
