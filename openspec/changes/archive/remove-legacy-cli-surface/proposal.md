## Why

The published `research-tree` command still exposes the retired filesystem
runtime and a standalone Alpha1 migration command. They are public compatibility
surfaces that can be discovered and invoked even though they are not the Alpha2
authority. The product decision is to abandon old-version compatibility rather
than preserve refusal, read-only, inventory, alias, or migration surfaces.

## What Changes

- **BREAKING**: Remove every legacy `research-tree` subcommand, including
  round, recursive-tree, and project-profile reads and writes.
- **BREAKING**: Retire the standalone `research-tree-migrate` console script,
  its modules, public exports, tests, and workflow-probe use.
- Remove legacy command registrations from public help, maintained
  documentation, authoring templates, and generated host packages.
- Keep only the minimal `research-tree` parser entrypoint; do not invent an
  unfinished canonical command surface or route into a coordinator.
- Register Alpha2 group 54 / issue #164 as a planned breaking-removal slice.

## Capabilities

### New Capabilities

- `legacy-cli-surface-removal`: Remove every published legacy CLI and migration
  surface without a compatibility response or replacement route.

### Modified Capabilities

- `canonical-runtime-contract`: Replace the legacy alias-or-refusal allowance
  with removal of the legacy public command surface.

## Impact

This change affects the CLI boundary, packaging entry points, the retired
Alpha1 migration implementation, focused tests, public documentation, source
templates, generated packages, and the Alpha2 execution registries. It adds no
canonical `run` verb, coordinator routing, HostEvent ingress, data migration,
dual write, or user-data mutation.

## Follow-up Boundary

`LegacyRunStoreImporter` and the remaining filesystem `RunStore` runtime are
not changed here. Their retirement is recorded in #165 and requires a separate
source-bound plan after this public-surface removal lands.
