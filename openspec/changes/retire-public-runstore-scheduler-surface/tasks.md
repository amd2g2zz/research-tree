## 1. Contract And Governance

- [x] 1.1 Define the current-only public scheduler retirement contract and the
  no-user-data-operation boundary.
- [x] 1.2 Register issue #178 / group 62 as a planned source-only deletion
  slice with an exact focused acceptance command.

## 2. Public Surface Removal

- [x] 2.1 Add a failing regression that proves the retired root scheduler
  symbols are absent.
- [x] 2.2 Delete root exports and the dedicated scheduler behavior suite
  without adding an alias, adapter, or replacement.
- [x] 2.3 Remove active registry, contract, and current documentation claims
  while retaining historical `docs/specs/RT-010.md` and the unreachable source
  module for #179.

## 3. Verification And Handoff

- [x] 3.1 Run the focused group-62 command, strict OpenSpec validation,
  governance validation, and full regression suite.
- [x] 3.2 Inspect the diff, commit green source changes, and record the
  source-bound receipt in the task-verification registry. Generated command
  output remains local-only and is located through the delivery-governance CI
  receipt rather than tracked in this source-only slice.
