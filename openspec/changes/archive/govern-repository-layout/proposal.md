## Why
The registry and ignore rules are not executable authority, so contributors cannot reliably distinguish source, generated packages, host copies, runtime state, evaluation evidence, and rebuildable output.

## What Changes
- Complete lifecycle metadata, deterministic read-only checking, clean-checkout probes, contributor guidance, and group-21 evidence without mutating user paths.

## Capabilities
### Modified Capabilities
- `repository-layout-governance`: Make the registry executable and report untracked installed, runtime, raw, and evaluation material without mutation.

## Impact
Affected: registry/schema, `.gitignore`, checker, tests, docs, and group-21 registries. Packages remain outputs; local runtime and installations remain outside checker mutation scope.
