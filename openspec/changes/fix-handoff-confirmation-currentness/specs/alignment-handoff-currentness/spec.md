## ADDED Requirements

### Requirement: A confirmation binds one final graph digest

The alignment controller SHALL record the digest of the graph state confirmed
for autonomous handoff after applying any internal acceptance transition. A
compiled handoff SHALL carry that digest as both its confirmation and compiled
graph digest when it is current.

#### Scenario: A confirmed graph is compiled without further mutation

- **WHEN** a ready alignment graph is confirmed with its displayed digest
- **THEN** the compiled handoff has equal confirmation and compiled graph
  digests

### Requirement: Post-confirmation graph mutations stale the handoff

The controller SHALL invalidate autonomous handoff state before committing a
subsequent graph merge or response record. It SHALL retain a structured stale
reason and require a new handoff confirmation before compilation.

#### Scenario: Authority changes after confirmation

- **WHEN** an authority-bearing node changes after handoff confirmation
- **THEN** compilation fails with a machine-readable stale-handoff error and a
  successor confirmation is required

### Requirement: Host adapters reject internally stale handoff artifacts

The native adapter SHALL reject an alignment handoff whose confirmation digest
does not equal its compiled graph digest before creating a host run.

#### Scenario: A stale handoff artifact is supplied to an adapter

- **WHEN** the handoff artifact carries different confirmation and compiled
  graph digests
- **THEN** adapter initialization fails without creating persistent run state
