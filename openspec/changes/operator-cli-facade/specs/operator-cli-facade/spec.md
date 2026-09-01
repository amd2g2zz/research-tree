## ADDED Requirements

### Requirement: Blueprint targets bind the compiled handoff at compile time

The canonical Blueprint Target compiler SHALL accept an optional alignment
handoff parent and, when provided, SHALL resolve it to the exact stored
`alignment-handoff` revision in the same run and append its artifact reference
to the compiled target's `parent_refs`. A handoff that is absent from the run,
stale, or of a foreign kind SHALL be rejected with a named error before any
write. When the parameter is omitted the compiled parent_refs SHALL be
unchanged.

#### Scenario: Compiled target carries the handoff lineage

- **WHEN** the compiler runs with a stored alignment-handoff revision
- **THEN** the appended blueprint target's parent_refs include the brief, the
  intent model, and that exact handoff reference, and
  `coordinator.initialize` accepts the target without any out-of-band write

#### Scenario: Foreign or missing handoff is rejected fail-closed

- **WHEN** the compiler is given an artifact that is not the run's stored
  `alignment-handoff` revision
- **THEN** compilation raises a named blueprint-target error and appends
  nothing

### Requirement: Operators initialize a run through the CLI

The CLI SHALL provide an `initialize` verb that, for a prepared run, resolves
the run's alignment handoff (compiling it through the existing alignment
handoff bridge when the alignment graph is confirmed), optionally compiles the
intent model and working brief from one operator document, compiles the
blueprint target with the handoff bind from one blueprint document, and drives
the canonical `coordinator.initialize`. Every failure SHALL surface as a named
canonical reason.

#### Scenario: Prepared run reaches initialized

- **WHEN** an operator runs `initialize` for a prepared run with a confirmed
  alignment graph, a working brief document, and a blueprint document
- **THEN** the run-state artifact exists with state `alignment` and the
  payload names the handoff, blueprint target, and (when authored) decision
  frame references

#### Scenario: Missing working brief is a named failure

- **WHEN** `initialize` runs for a run with no working-brief document and no
  working brief in the ledger
- **THEN** the CLI fails with the canonical reason `working_brief_missing`

### Requirement: Operators drive the strategy gates from the CLI

The CLI `strategy propose` verb SHALL accept an optional independent alignment
verification document, registered through the canonical completion-input
registrar, and SHALL accept a base projection document whose display payload,
display digest, and content hash are computed by the product, so that
`propose`, `display`, and `confirm` complete from operator surfaces with the
existing gates unchanged.

#### Scenario: Propose-to-confirm completes without Python internals

- **WHEN** an operator proposes a base projection with an independent
  alignment verification document, then runs `strategy display` and
  `strategy confirm` with the digest-bearing authorization
- **THEN** the run's strategy confirmation completes and the research tree
  lifecycle advances without any direct Python API call

### Requirement: Operators read the operating model from the CLI

The CLI SHALL provide an `operating-model` verb that renders the run's Human
Brief operating model — roles, SLA, concurrency limits, blockers, outcome
layers, adoption metrics, fallback plan — from the canonical delivery
compiler as markdown without requiring any Python API call.

#### Scenario: Operating model renders operator sections

- **WHEN** `operating-model` runs for any existing run
- **THEN** the output names the Roles, SLA, Concurrency limits, Blockers,
  and Fallback plan sections and mirrors the coordinator's blockers verbatim

### Requirement: The packaged alignment controller records speech acts

The shipped alignment controller script SHALL execute `record` successfully in
the packaged layout: the speech-act module ships beside it, and the lazy
speech-act imports resolve both as a package-relative import and as a sibling
module import.

#### Scenario: Packaged record reaches rc 0

- **WHEN** the packaged `scripts/alignment_controller.py record` command runs
  in a subprocess against an initialized, planned alignment graph
- **THEN** the command exits 0 and reports the recorded turn
