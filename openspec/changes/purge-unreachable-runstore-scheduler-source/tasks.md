## 1. Deletion Contract

- [ ] 1.1 Define the current-only scheduler source-removal contract and
  explicitly exclude shared registry and parent-tracker changes.
- [ ] 1.2 Add a failing structural regression for absent source, imports,
  obsolete contract, and generated-package references.

## 2. Scheduler Purge

- [ ] 2.1 Delete the unreachable RunStore scheduler implementation and the
  obsolete RT-010 public contract without a compatibility path.
- [ ] 2.2 Update the focused retirement regression to prove only the deleted
  boundary is absent while historical delivery evidence remains untouched.

## 3. Verification

- [ ] 3.1 Run focused deletion, packaging, OpenSpec, lint, and format checks.
- [ ] 3.2 Run the full test suite and record the unallocated #179 receipt
  conflict for the release-train owner without modifying shared registries.
