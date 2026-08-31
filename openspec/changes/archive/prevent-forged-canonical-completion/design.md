## Context

Issues #156, #157, and #158 delivered typed completion-input registration,
delivery-and-acceptance registration, and deterministic manifold resolution.
Their parent, #149, requires one source-bound acceptance surface that proves
the three child receipts are reachable together and that the completed runtime
does not regress to generic ledger artifacts or stale completion state.

## Goals / Non-Goals

**Goals:**

- Bind group 36 to reachable receipts for groups 43, 44, and 45.
- Exercise the delivered runtime boundary through a parent-level false-
  completion acceptance test.
- Record the parent-only source-bound verification after the final acceptance
  source commit.

**Non-Goals:**

- Changing canonical writers, `RunLedger`, coordinator completion logic, or
  the public CLI.
- Replacing child-group tests or adding a compatibility path.
- Closing child issues or recording their evidence again.

## Decisions

### Verify the integrated boundary instead of duplicating child implementation

The parent test reads the Alpha2 registries, checks the exact child-receipt
revisions are ancestors of its source revision, and runs the already-delivered
completion-manifold regression suite. This keeps one implementation owner for
each child boundary while making the parent release claim independently
auditable.

### Keep completion evidence local and source-bound

Group 36 records generated receipt and output paths under
`.research-tree/verification-runs/`. The registry retains only their local
references and the command's source revision and digests. This prevents a
tracked generated receipt from becoming an alternative authority surface.

### Treat a reopened manifold as a required parent invariant

The acceptance command includes the manifold and coordinator tests that prove
generic lookalikes cannot complete a run, valid registered inputs complete
idempotently, and superseded or quarantined parents reopen the current
completion state while preserving immutable history.

## Risks / Trade-offs

- A child receipt can become unreachable after a history rewrite -> verify each
  child source revision with `git merge-base --is-ancestor` in the parent test.
- Parent tests could duplicate child behavior -> invoke the existing focused
  child suites and add only registry/reachability assertions.
- A local receipt is unavailable on another machine -> keep the registry
  source-bound and rerun its recorded command there rather than trusting copied
  output.

## Migration Plan

No data migration is required. Roll back by reverting the parent acceptance
and group-36 registry entry; the child completion boundaries remain immutable
and non-authoritative generic artifacts remain blocked.
