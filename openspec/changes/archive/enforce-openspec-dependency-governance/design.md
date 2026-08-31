## Context

The Alpha2 umbrella change contains a task checklist, a task-group registry, and
a capability delivery matrix. They currently disagree: the matrix refers to
groups 25--27 that are absent from the registry, newer implementation issues do
not have a single authoritative group mapping, and the existing validator checks
document shape and cycles without checking dependency completion semantics.
Several individual task checkboxes are already checked even though their group
dependencies have not been verified. A green structural check is therefore not
evidence of a verified implementation slice.

This change is a governance implementation, not a claim that any Alpha2 runtime
capability is complete. It must run from source and installed package checkouts
without reading user-owned runtime data.

## Goals / Non-Goals

**Goals:**

- Define one machine-readable lifecycle for Alpha2 task groups.
- Require evidence-bearing verification before a group can become `verified`.
- Reject invalid dependency states, unresolved task-group references, issue
  ownership conflicts, and dependency cycles with stable diagnostics.
- Repair the current issue/group/capability graph, including groups 23--32.
- Generate a deterministic governance report used by local and release checks.

**Non-Goals:**

- Implement Alpha2 runtime capabilities or retroactively mark them verified.
- Close GitHub issues from a validator.
- Infer evidence from checkbox text, report length, branch state, or CI labels.
- Delete, rewrite, or migrate user-owned worktrees and runtime artifacts.

## Decisions

### Separate plan state from verification state

`tasks.md` remains a human-readable implementation plan. A new
`task-verification-v1.json` is authoritative for each group state:
`planned`, `in_progress`, `blocked`, `unavailable`, `verified`, or
`superseded`. Only `verified` represents completed implementation. A group in
any other state remains incomplete, including `unavailable`.

Every verified group records immutable evidence references, a command receipt
with command, exit code, environment digest, and output digest, plus a rollback
disposition. The validator rejects `verified` without complete evidence.

Alternative considered: infer completion from all checked Markdown tasks.
Rejected because a checklist has no dependency, environment, or artifact
integrity semantics and is easy to update independently of execution.

### Make dependency closure a graph invariant

The validator loads task groups into a directed graph. A `verified` group MUST
have every direct and transitive dependency in `verified`; a group MAY be
`blocked` or `unavailable` when a dependency is not verified, but cannot claim
completion. The validator reports the shortest violating dependency path.

Alternative considered: validate only direct dependencies. Rejected because it
allows a verified parent to hide an incomplete ancestor through an intermediate
group.

### Centralize issue and capability ownership

`issue-execution-map-v1.json` assigns each tracked Alpha2 issue a primary group,
zero or more supporting groups, owned capability identifiers, and an explicit
OpenSpec change. A group has one primary issue owner. A capability row may name
multiple supporting groups but every referenced group and issue mapping MUST
resolve. The validator rejects duplicate primary ownership and a row that points
to a group owned by an unrelated issue.

Alternative considered: continue parsing GitHub issue prose. Rejected because
remote issue text is mutable, not available offline, and cannot be release
evidence.

### Repair the graph before enforcing completion

The registry gains groups 23--32. Group 20 (evaluation asset governance) depends
only on the Alpha1 baseline group, removing the historical #69/#55/#64 cycle.
Group 30 owns paired Alpha1/Alpha2 benchmark comparison (#84) and depends on
the cross-host harness group 12; group 12 owns deterministic black-box harness
and release gates (#64). Alignment work is split as group 7 (#59 action
selection), group 31 (#87 DecisionFrame), group 23 (#73 correction
invalidation), and group 28 (#85 strategy projection/handoff). Group 28 does
not depend on groups 12 or 24, eliminating the #85/#64/#72 cycle.

Alternative considered: collapse all newer issues into their nearest existing
group. Rejected because it hides independently reviewable behavior behind a
large umbrella issue and prevents issue-isolated delivery.

### Treat unavailable evidence as first-class, not as success

The verification record may explain unavailable host, provider, or external
evaluation evidence. The validator retains that record and exposes its blocker
in the report, but never promotes it to `verified` or allows release completion
to consume it as evidence.

Alternative considered: accept a skipped command with a note. Rejected because
it recreates the false-completion path the Alpha2 program is intended to remove.

## Risks / Trade-offs

- **[Registry migration invalidates current checked tasks]** -> Preserve task
  checkboxes as plan history; initialize every group as `planned` unless a
  complete verification record exists.
- **[Graph rules make planning temporarily blocked]** -> Report exact missing
  group, evidence, and dependency path; do not silently rewrite state.
- **[Issue map becomes stale]** -> Validate every registered Alpha2 issue in the
  local release registry and fail unknown/missing mappings in CI.
- **[Governance validator becomes a second runtime authority]** -> Limit it to
  repository planning and release evidence; it cannot mutate ResearchRun state.
- **[Existing release scripts are unavailable]** -> Record them as unavailable
  baseline checks, not passing checks, until their owning issue implements them.

## Migration Plan

1. Add valid and invalid fixtures that describe the current structural gaps.
2. Define schemas and static registry entries for task groups, verification
   records, issue ownership, and report output.
3. Implement the pure parser and graph validator, then a CLI wrapper.
4. Repair task execution, delivery-matrix, and issue map entries in one
   migration commit; initialize all unproven groups as `planned`.
5. Add the validator to delivery/release checks after its own tests pass.
6. Roll back by removing the new CI invocation; registries and reports remain
   read-only evidence and no runtime state requires reversal.

## Open Questions

- The #67 milestone membership source is currently remote GitHub metadata. The
  initial validator will consume a checked-in Alpha2 issue registry for
  deterministic offline validation; a later release tool may compare it with
  GitHub as a separate, explicitly unavailable-capable check.
