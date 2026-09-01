## ADDED Requirements

### Requirement: Release gate validation lives in the harness, not the runtime package

The runtime package SHALL NOT contain `release_evaluation.py`, and the root
package SHALL NOT re-export `IntegrityGate`, `InvalidReleaseManifest`,
`ReleaseCaseResult`, `ReleaseDecision`, `ReleaseManifest`, or
`evaluate_release`. The release gate module SHALL live at
`evaluation/harness/release_evaluation.py` as a byte-identical relocation
registered under the tracked evaluator-code class of `evaluation-paths-v1`.

#### Scenario: A caller follows the former runtime import path

- **WHEN** a caller attempts `research_tree.release_evaluation` or resolves any
  former root re-export of the release gate symbols
- **THEN** the resolution fails and no alias, facade, bridge, adapter, shim, or
  umbrella re-export remains in the runtime package

### Requirement: The harness entrypoint imports its harness sibling

`evaluation/harness/run_release_gates.py` SHALL import `ReleaseManifest` and
`evaluate_release` from the harness sibling module (the `run_host_conformance`
same-directory precedent) instead of the root package, so the registry
entrypoint command text stays unchanged.

#### Scenario: The release gate entrypoint runs

- **WHEN** `uv run python evaluation/harness/run_release_gates.py` executes or
  the retained candidate manifest is replayed
- **THEN** the deterministic decision is identical to the pre-migration replay
  and no `research_tree` import is required

### Requirement: evaluation.py keeps only its consumed validation surface

`src/research_tree/evaluation.py` SHALL retain exactly the symbols consumed by
production code — `BLUEPRINT_EVALUATION_KIND` and
`validate_blueprint_evaluation_payload` (imported by
`completion_inputs.write_evaluation`) — plus their direct dependencies
(`EvaluationError`, `InvalidEvaluationError`, `TimeSplitCase`,
`EvaluationDiagnosis`, and validation helpers). The un-exercised suite,
runner, request/result protocol, and `BlueprintEvaluationSuite` SHALL be
absent.

#### Scenario: A maintainer audits the shrunk module surface

- **WHEN** production imports of `research_tree.evaluation` are enumerated
  (`completion_inputs.py` deferred import and the root re-export block) and
  each retained symbol is traced to a consumer
- **THEN** every retained symbol resolves to the completion-input evaluation
  write path, and the deleted suite symbols have no src/ consumer

### Requirement: Retirement leaves no dangling references

Source, tests, and live entrypoints SHALL NOT reference the former
`src/research_tree/release_evaluation.py` path or the deleted evaluation
symbols. Harness tests SHALL import the relocated module via the harness
sys.path precedent, and surviving suites SHALL NOT import or exercise deleted
symbols.

#### Scenario: Reference sweep after the migration

- **WHEN** maintainers grep `src/`, `scripts/`, `hooks/`, and `tests/` for
  `release_evaluation` and the deleted evaluation symbols
- **THEN** the only `release_evaluation` hits are the relocated module and its
  harness consumers, and no test references a deleted symbol
