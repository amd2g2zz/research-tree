## Context

`ResearchRunCoordinator.apply_correction()` currently chooses quarantined
artifacts through `CORRECTION_DEPENDENT_KINDS`. New kinds and unknown
intermediate parents can bypass that list even when they descend from a
corrected decision.

## Goals / Non-Goals

**Goals:**

- Traverse immutable artifact-parent lineage from each correction target.
- Classify every reachable canonical descendant conservatively, including an
  unknown intermediate kind.
- Preserve independent branches and expose a stable stale path for rejection.

**Non-Goals:**

- Deleting history, changing the public CLI, or reimplementing #151 HostEvent
  ingress.

## Decisions

- Use ledger parent references as the dependency graph, not a kind allowlist.
- Quarantine every descendant of a corrected root unless a graph branch is
  demonstrably independent; unknown kinds fail closed when reachable.
- Retain a deterministic predecessor chain so dispatch, ingress, recovery, and
  completion can return the same stale diagnostic after restart.

## Risks / Trade-offs

- [Parent metadata is malformed] -> reject authority rather than guessing a
  branch is independent.
- [A broad traversal quarantines too much] -> begin only at exact correction
  roots and preserve artifacts with no path from those roots.
