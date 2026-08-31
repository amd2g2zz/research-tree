## ADDED Requirements

### Requirement: Trace emission is a single fail-open writer

The debug trace emitter SHALL be a single small fail-open writer inside
`src/research_tree/lifecycle_hook.py` (within a 150-line budget including its
helpers and vocabularies). The runtime SHALL NOT carry debug-trace protocol
objects, causal replay machinery, a trace summary command, or a standalone
debug CLI. The retired `debug_trace` module name SHALL produce zero grep hits
in `src/`, `scripts/`, and `hooks/` Python sources outside the lifecycle_hook
emitter definitions.

#### Scenario: Retired module and CLI are gone

- **WHEN** maintainers inspect `src/research_tree/` and the pyproject script
  entry points
- **THEN** `debug_trace.py` does not exist, no `research-tree-debug` entry
  point remains, and
  `grep -rn "debug_trace" src/ scripts/ hooks/ --include="*.py"` reports hits
  only inside the lifecycle_hook emitter definitions

#### Scenario: Hook debug emission stays fail-open

- **WHEN** the lifecycle hook observes with `debug=True` and the trace writer
  raises (`OSError` or `ValueError`)
- **THEN** the observation still returns `recorded`, the host response is
  unchanged, and no session is blocked

### Requirement: Trace records stay sanitized and bounded

Each trace record SHALL contain only the fixed sanitized fields
(`schema`, `source`, `recorded_at`, `host`, `phase`, `status`, `codes`, and an
optional `run_id`); codes and identifiers SHALL be bounded diagnostic tokens,
and records SHALL NOT contain prompts, tool inputs, responses, secrets, or
free-form text.

#### Scenario: Emitted record carries only structured fields

- **WHEN** the emitter persists a trace record
- **THEN** the record matches the fixed sanitized field set exactly, with
  bounded codes and no transcript fields

### Requirement: Governance and docs carry zero retired-surface residue

Governance command pairs SHALL NOT name retired test or source paths; the
delivery-matrix `runtime-observability` row SHALL point at
`src/research_tree/lifecycle_hook.py` with the hook debug emission surface;
the path registry SHALL name `research-tree-hook --debug` as the canonical
command for `.research-tree-debug/`; skill templates and operator docs SHALL
NOT name the retired CLI. Receipt digests, source_revision, and recorded_at
are historical records and are not rewritten.

#### Scenario: Command pairs stay identical after pruning

- **WHEN** a maintainer compares each pruned group 11/36/45/63
  `acceptance_command` with its paired verification receipt command
- **THEN** the two commands are verbatim identical and name no retired path

#### Scenario: Docs and packages name no retired CLI

- **WHEN** maintainers read `references/debug-tracing.md`, the skill
  templates, and packaged SKILL.md files
- **THEN** `research-tree-debug` SHALL NOT appear in any packaged skill or
  active operator documentation
