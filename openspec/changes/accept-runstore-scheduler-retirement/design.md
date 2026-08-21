## Context

Issue #178 removed every supported scheduler surface and issue #179 removed
the retained source module and obsolete `RT-010` contract. The child groups are
verified independently, but the parent tracker needs a small, current-baseline
receipt before it can close.

## Goals / Non-Goals

**Goals:**

- Bind #175 to child groups 62 and 76 only after their source-bound receipts
  are ancestors of the parent baseline.
- Keep one focused parent acceptance test that checks registry ownership and
  the completed structural absence boundary.
- Record a new group-78 receipt without rewriting the child receipts.

**Non-Goals:**

- Recreate, modify, or otherwise touch a scheduler implementation.
- Add a replacement, alias, facade, bridge, adapter, dual write, migration,
  fallback, or compatibility reader.
- Read, move, delete, repair, or migrate user-owned runtime data.
- Change the completed #178 or #179 source, registry definitions, or receipts.

## Decisions

### Parent evidence consumes immutable child receipts

Group 78 depends on groups 62 and 76. The parent test checks that each child
receipt has a source revision reachable from the parent `HEAD`; it does not
substitute a new implementation test or amend a child record.

### Existing child absence coverage remains authoritative

The parent command runs the completed child absence suite along with one
parent-only registry test. This preserves the child test as the proof that no
runtime import, public contract, dedicated behavior suite, or generated
package exposes the retired boundary.

### The parent records metadata only

The delivery-matrix row names only the new acceptance test and publishes no
public surface. Rollback is a Git revert of parent metadata and never restores
the deleted boundary or performs a data operation.

## Risks / Trade-offs

- [A child receipt is verified but not reachable] -> require the parent test
  to check each source revision with `git merge-base --is-ancestor`.
- [A registry change reintroduces a scheduler claim] -> run the existing child
  absence test in the parent acceptance command.
- [Parent evidence expands into implementation work] -> constrain its source
  modules to tests and OpenSpec/registry records only.

## Migration Plan

No migration exists. Add the parent registry plan and failing acceptance test,
run the registered command at its source commit, then bind its local-only
receipt. Reverting this parent PR removes only the parent evidence metadata;
it never restores a scheduler or mutates user-owned data.
