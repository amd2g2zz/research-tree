## Why

Alpha2 task group 14 is still planned even though issue #66 ratified its architecture contract, because its registered acceptance command does not exist and the umbrella task text claims entities owned by downstream groups 25-27. This prevents downstream work from depending on a truthful, executable contract gate.

## What Changes

- Narrow group 14 to the already ratified architecture, lifecycle, and registry boundaries owned by issue #66.
- Add a tracked `scripts/validate_contracts.py` acceptance entrypoint that runs the ratification checks against repository sources.
- Extend OpenSpec governance tests so acceptance entrypoints must resolve and dependency graphs reject cycles.
- Record a source-bound group 14 verification receipt while leaving groups 25-27 planned.

## Capabilities

### New Capabilities

- `contract-verification-governance`: Defines executable acceptance-entrypoint, dependency ownership, and source-bound receipt requirements for task-group verification.

### Modified Capabilities

None.

## Impact

The change affects the Alpha2 umbrella task and verification registries, the OpenSpec governance test boundary, a new contract-validation script, and evidence stored under this change. It does not add or change runtime schemas, source capture, native workflows, or search behavior.
