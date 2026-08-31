## ADDED Requirements

### Requirement: Batch-2 graph-verified dead modules are absent

The package SHALL NOT contain `assurance.py`, `preferences.py`,
`alignment_protocol.py`, `durable_interaction_state.py`, or
`interaction_state.py`, and the root package SHALL NOT re-export any symbol
from them. Retirement SHALL be evidence-based: zero production CALLS edges in
the code graph cross-confirmed by text grep.

#### Scenario: A caller imports a retired batch-2 module path

- **WHEN** a caller attempts to import any retired module or resolves its
  former root re-exports
- **THEN** the import fails and no alias, facade, bridge, adapter,
  replacement, migration, fallback, or user-data operation exists

### Requirement: Batch-2 retired src paths survive only as relocations

`src/research_tree` SHALL NOT contain `openspec_governance.py` or
`context_ledger.py`. Each is retired from the runtime package as a
byte-identical relocation with a live hard consumer, and the relocation SHALL
be recorded: `scripts/openspec_governance.py` (CI delivery-gate dependency)
and `scripts/context_ledger_contract.py` (the packaged adapter contract whose
context-receipt subcommands remain live and covered by the execution-adapter
suites).

#### Scenario: A maintainer traces a relocated module

- **WHEN** a caller follows the former `research_tree.openspec_governance` or
  `research_tree.context_ledger` import path, or a skill package is rebuilt
- **THEN** the governance wrapper and tests resolve the scripts-module
  location, the adapters resolve the sibling contract module, and the
  packaged context-receipt behavior is unchanged

### Requirement: Retirement leaves no dangling references

Source, active governance registries, and live acceptance commands SHALL NOT
reference the retired modules. The lifecycle hook SHALL keep recording events
without the durable interaction state mirror; no surviving suite SHALL import
or exercise the retired modules; `research_tree` SHALL NOT re-export any
retired symbol.

#### Scenario: Reference sweep after retirement

- **WHEN** maintainers grep `src/`, `scripts/`, `hooks/`, and `tests/` for the
  retired module names and inspect import statements
- **THEN** zero real references remain outside the recorded relocation paths
  (name coincidences in prose or local variable names are not references)

### Requirement: Governance registries stay consistent with deletion

Active acceptance commands and their paired verification receipts SHALL only
name entrypoint paths that exist. Deleting or relocating a module SHALL be
accompanied by updating the alpha2 registry command pairs it appeared in,
without falsifying recorded receipts beyond the command-pairing requirement.

#### Scenario: Governance validation runs after module deletion

- **WHEN** `scripts/check_openspec_governance.py` validates the registries
  after a retired module path is removed from a group's acceptance command
  and its paired receipt
- **THEN** no `missing_acceptance_entrypoint` or
  `verified_record_incomplete` violation is reported
