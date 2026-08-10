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
- Record current receipts and mark only groups 1, 2, 33, and 34 verified.
- Record group 3 as blocked with its strict-evidence successor #106; preserve
  group 14 as planned.

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
- Does not alter runtime behavior or falsely reclassify broad contract group 14.
