## Context

Issue #83 was split into the deliberately narrow #185 planning, #186 execution,
and #187 canonical-lineage deliveries. Their groups 74, 75, and 77 are merged,
but the original group-27 definition still describes a retired change and a
legacy rollback path. PR #217 used a squash merge, so group 74's first receipt
points to an equivalent source commit that is not an ancestor of `dev`.

The old PR #147 comparison is a placeholder fixture with synthetic digests and
deleted code references. It is retained only as audit history and cannot prove
the current implementation.

## Goals / Non-Goals

**Goals:**

- Define one parent-only group-27 acceptance that exercises the delivered child
  suites together and records a source-bound receipt at the final parent head.
- Re-run group 74's unchanged command at reachable merge `34d1c2b` and record
  the resulting receipt fields before the parent consumes that dependency.
- Add a deterministic comparison fixture that derives its four published
  deltas from public, normalized observation identifiers and labels its retired
  direct-query side as static historical evidence only.
- Update issue/group/capability metadata to current modules and Python public
  APIs, with no public CLI claim that no longer exists.

**Non-Goals:**

- Reimplement or change the #185, #186, or #187 runtime behavior.
- Restore direct-query code, a legacy schema/reader, a compatibility adapter,
  an acquisition fallback, or a second persistence writer.
- Modify the retained release manifest, claim a release pass, or treat this
  deterministic comparison as live-provider evidence.

## Decisions

### Parent verification consumes delivered child groups

Group 27 will depend directly on verified groups 74, 75, and 77. The issue map
will retain group 15 as the existing supporting durable-acquisition capability.
Its command will run the child focused observable suites plus one parent comparison test,
format/lint the relevant current modules and tests, and run governance. Full
regression, strict OpenSpec validation, package checking, and the hosted
delivery gate remain pre-merge requirements but are not substituted for the
group receipt.

This makes the parent a composition boundary rather than a fourth portfolio
implementation surface.

### Group-74 source binding is repaired at its squash merge

The parent carries a metadata-only rebind for group 74. It uses the exact
already-registered command, its successful output generated at `34d1c2b`, and
the reachable merge revision in the command receipt. No source files or
planner behavior are modified. The original receipt remains superseded
governance history rather than evidence for the final parent gate.

Re-running at the merge commit is chosen over changing the old receipt's hash
without execution or creating a new issue solely for adjacent receipt data.

### Comparison is static and current-only

The new fixture uses a declared normalized input and two sets of public
observation identifiers. The test derives:

- rediscovery from duplicate observation identifiers;
- coverage from the number of covered declared subquestions;
- depth from an explicit finite depth rank; and
- decision closure from an explicit bounded outcome.

It verifies the published deltas rather than trusting precomputed values. The
retired baseline is data only; it contains no import path, executable command,
raw query text, private prompt, or adapter reference. A forward link to the
retained release manifest is contextual only, and the fixture states that it
does not change that manifest or establish a release decision.

### Registry rows name current public surfaces

The delivery matrix will name `search_portfolio.py`, `source_capture.py`, and
`coordinator.py` plus their real public service methods. It will remove stale
`acquisition.py`, `methods.py`, and `research-tree run plan-search` claims.
The group rollback is a Git revert of parent acceptance metadata only and
explicitly forbids restoring retired behavior.

## Risks / Trade-offs

- [Static baseline could be mistaken for live quality evidence] -> require
  explicit `static_historical_baseline` classification, limitations, and a
  non-release link in the fixture and test.
- [A child receipt could be syntactically verified but unreachable] -> assert
  the repaired group-74 source and the existing group-75/77 source revisions
  are ancestors of the parent baseline before recording group 27.
- [Registry edits could describe obsolete public behavior] -> test exact
  current module/public-surface strings and preserve no CLI entry for planning.
- [Parent scope could grow into a new implementation slice] -> limit changed
  runtime files to none; all behavioral coverage runs existing child tests.

## Migration Plan

No runtime data migration exists. First record the group-74 rebind as local
verification evidence, then update parent metadata and test/fixture, run the
aggregate command, and record group 27. Rollback is a Git revert of the parent
acceptance PR; child artifacts and historical static baseline material remain
read-only, while no legacy runtime path is restored.
