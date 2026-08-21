## Why

Merged Alpha2 foundation code is not automatically verified work. The registry
currently combines complete and incomplete responsibilities under the same task
groups and stores only state labels, which makes both false completion and false
blocking likely.

## What Changes

- Add reproducible verification receipts bound to a task group, exact acceptance
  command, source revision, environment digest, output digest, evidence paths,
  and rollback disposition.
- Tighten governance so a `verified` state rejects a substituted command or
  malformed receipt.
- Reconcile task-group 2 to the implemented SQLite ledger responsibility,
  retaining CAS and legacy import in their explicitly split groups 33 and 34.
- Record current receipts for groups 1, 2, 3, 33, 34, and a dedicated
  integration group 35. Group 35 binds the merged strict slices and the
  future-evidence-gap inventory without claiming later runtime groups.
- Preserve group 14 and groups 4-32 as planned; #56/OracleRun remains open.

## Capabilities

### New Capabilities

- `verification-receipts`: Reproducible, source-bound evidence for task-group
  verification state.

### Modified Capabilities

- `implementation-release-contract`: Require task verification to bind the
  declared acceptance command and exact source revision.

## Impact

- Affects OpenSpec governance parsing, its CLI/helper, task execution and
  verification registries, focused governance tests, and retained raw command
  output under the Alpha2 change evidence directory.
- Does not alter runtime behavior or falsely reclassify broad contract group 14
  or OracleRun (#56).
