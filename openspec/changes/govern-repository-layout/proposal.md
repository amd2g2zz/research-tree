## Why

The repository has a path registry and partial ignore rules, but neither is a
complete executable authority model.  Contributors cannot reliably distinguish
authoring source from generated packages, installed host copies, runtime state,
evaluation evidence, and rebuildable output, so supported workflows can leave
unexplained checkout state or invite unsafe cleanup.

## What Changes

- Complete the repository path registry with lifecycle metadata and an entry for
  every supported top-level path, including tracked root files and ignored local
  state.
- Add a deterministic, read-only layout checker that validates registry shape,
  checkout coverage, ignore policy, and generated-package boundaries with stable
  diagnostics.
- Define clean-checkout probes for package validation and safe local artifacts
  without deleting, moving, staging, or otherwise mutating user-owned paths.
- Document path authority, rebuild and install boundaries, and non-destructive
  migration guidance for contributors.
- Register group 21 verification evidence once the focused and cross-boundary
  acceptance checks pass.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `repository-layout-governance`: Make the path registry executable, complete
  the clean-checkout boundary, and require non-destructive diagnostics for
  untracked installed, runtime, raw, and evaluation material.

## Impact

Affected surfaces are the Alpha2 path registry and schema, `.gitignore`, a new
`scripts/check_repository_layout.py` checker, focused tests, contributor
documentation, and the group-21 execution and verification registries.
Generated host packages remain generated outputs and repository-local runtime
or installed copies remain outside checker mutation scope.
