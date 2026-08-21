## 1. Deletion Contract

- [x] 1.1 Define the current-only scheduler source-removal contract and limit
  governance work to the dedicated group-76 receipt without parent-tracker changes.
- [x] 1.2 Add a failing structural regression for absent source, imports,
  obsolete contract, and generated-package references.

## 2. Scheduler Purge

- [x] 2.1 Delete the unreachable RunStore scheduler implementation and the
  obsolete RT-010 public contract without a compatibility path.
- [x] 2.2 Update the focused retirement regression to prove only the deleted
  boundary is absent while historical delivery evidence remains untouched.

## 3. Verification

- [x] 3.1 Run focused deletion, packaging, OpenSpec, lint, and format checks.
- [x] 3.2 Run the full test suite and bind the registered group-76 local
  source-bound receipt without modifying group 62 or parent #175.
