## Context

Issue #180 moved decision, delivery, and strict-delivery Finding Pack test
consumers to direct canonical fixtures. Issue #181 then moved readiness and
strict-evidence consumers. Their source-bound receipts are reachable from
`dev`, but #171 needs a single parent-only acceptance record.

## Goals / Non-Goals

**Goals:**

- Bind #171 to groups 79 and 80 only after both child receipt revisions are
  ancestors of the parent baseline.
- Preserve one focused parent acceptance test for receipt reachability and
  ownership metadata.
- Record a new group-81 receipt without rewriting a child receipt.

**Non-Goals:**

- Delete, modify, or otherwise retire `FindingPackCompiler`.
- Modify runtime source, test fixtures, or the #180/#181 child test suites.
- Add a runtime adapter, bridge, fallback parser, alias, dual store, or
  exported compatibility helper.
- Change assurance or exporter legacy-coverage boundaries.

## Decisions

### Parent evidence consumes immutable child receipts

Group 81 depends on groups 79 and 80. The parent test requires each child
verification record to be verified and its source revision to be an ancestor
of `HEAD`; it never substitutes a new child implementation test or amends a
child record.

### Existing lineage proofs remain authoritative

The parent command reruns the existing static lineage tests from the two child
slices together with its registry test. This confirms the named canonical
consumers stay clear of the retired fixture paths without changing runtime
behavior.

### The parent records metadata only

The delivery-matrix row names only the parent acceptance test and publishes no
public surface. Rollback is a Git revert of parent metadata and retains the
immutable child evidence.

## Risks / Trade-offs

- [A child receipt is verified but not reachable] -> require a
  `git merge-base --is-ancestor` check for each source revision.
- [Registry metadata overclaims the migration] -> assert the exact parent
  dependency, ownership, capability, and source-module rows.
- [Parent evidence expands into migration work] -> limit changed files to the
  new test, OpenSpec, and governance records.

## Migration Plan

No migration exists. Add the planned parent registry boundary and failing
acceptance test, run the exact command from its source commit, then bind the
local-only source-bound receipt. Reverting this parent change removes only the
parent evidence metadata; it never restores or changes a runtime path.
