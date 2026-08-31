## ADDED Requirements

### Requirement: Graph-verified dead modules are absent

The package SHALL NOT contain `alpha1_adversarial.py`, `best_of_n.py`,
`black_box_regression.py`, `progress_delta.py`, `state_projection.py`,
`operating_model.py`, `cognition.py`, `growth.py`, `native_workflows.py`,
`shared_brief.py`, `context_cost.py`, or `schemas.py`, and the root package
SHALL NOT re-export any symbol from them. Retirement SHALL be evidence-based:
zero production CALLS edges in the code graph cross-confirmed by text grep.

#### Scenario: A caller imports a retired module path

- **WHEN** a caller attempts to import any retired module or resolves its
  former root re-exports
- **THEN** the import fails and no alias, facade, bridge, adapter,
  replacement, migration, fallback, or user-data operation exists

### Requirement: Retirement leaves no dangling references

Source, active governance registries, and live acceptance commands SHALL NOT
reference the retired modules. `problem_forest` SHALL NOT import or annotate
against `cognition`; `coordinator.confirm_handoff` SHALL NOT expose a growth
`branch` parameter; `alignment_protocol` SHALL NOT import `growth` or expose
`growth_aware_readiness`.

#### Scenario: Reference sweep after retirement

- **WHEN** maintainers grep `src/`, `scripts/`, and `hooks/` for the retired
  module names and inspect import statements
- **THEN** zero real references remain (name coincidences in prose or local
  variable names are not references)

### Requirement: Governance registries stay consistent with deletion

Active acceptance commands and their paired verification receipts SHALL only
name entrypoint paths that exist. Deleting a module SHALL be accompanied by
removing its path from the alpha2 registries it appeared in, without
falsifying recorded receipts beyond the command-pairing requirement.

#### Scenario: Governance validation runs after module deletion

- **WHEN** `scripts/check_openspec_governance.py` validates the registries
  after a retired module path is removed from a group's acceptance command
  and its paired receipt
- **THEN** no `missing_acceptance_entrypoint` or
  `verified_record_incomplete` violation is reported
