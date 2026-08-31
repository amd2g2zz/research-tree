## ADDED Requirements

### Requirement: The public CLI invokes only settled coordinator operations

The `research-tree` entrypoint SHALL publish only `research-tree run ingest`,
`recover`, `why-not-complete`, and `complete`. Each command SHALL construct one
`RunLedger` from the explicit workspace and invoke the corresponding
`ResearchRunCoordinator` operation directly. It SHALL not register an alias,
legacy command, generic lifecycle dispatcher, delivery/acceptance composition,
or read projection.

#### Scenario: HostEvent ingress matches the coordinator

- **WHEN** a caller supplies one valid HostEvent JSON envelope and an explicit
  workspace to `research-tree run ingest`
- **THEN** the emitted artifact JSON equals the result of
  `ResearchRunCoordinator.ingest_host_event()` against that workspace

#### Scenario: Completion remains coordinator-owned

- **WHEN** a caller invokes `why-not-complete`, `recover`, or `complete` with
  the required current inputs
- **THEN** the CLI result is the direct coordinator result or its stable
  canonical error classification

### Requirement: CLI responses use a deterministic current-only JSON contract

Every successful or coordinator-rejected command SHALL emit one JSON object to
stdout containing `code`, `category`, `retryability`, `run_id`,
`safe_message`, `unmet_obligations`, `evidence_refs`, and `next_action`.
Stale revisions SHALL exit 3, unmet completion obligations SHALL exit 4, and
invalid input or HostEvent protocol errors SHALL exit 2. Parser rejection of an
unknown command SHALL occur before a workspace is opened.

#### Scenario: Retired or unsupported verbs are absent

- **WHEN** a caller asks for CLI help or invokes a retired command, `deliver`,
  `accept`, `reconcile-host`, or `status`
- **THEN** argparse rejects the unregistered verb without creating the supplied
  path or emitting a compatibility response
