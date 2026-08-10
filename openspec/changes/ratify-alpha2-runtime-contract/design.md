## Context

The active Alpha2 change already defines the intended coordinator, storage,
graph, and host boundaries. However, only ADR-001 exists in `dev`; the decision
records named by #66 are absent. A stale feature branch contains drafts, but it
is neither an integration base nor evidence of ratification.

## Goals / Non-Goals

**Goals:**

- Publish four self-contained ADRs that agree with the active Alpha2 design.
- Make the contract's normative cross-references executable: ADRs, lifecycle
  matrix, capability specs, issue map, and delivery matrix must resolve.
- Keep architectural decisions reviewable independently of future runtime code.

**Non-Goals:**

- Implement a coordinator, host events, evidence, or closure behavior.
- Mark task group 14 verified or declare Alpha2 release-ready.
- Promote unmerged feature-branch artifacts without review.

## Decisions

### Four narrow ADRs are the normative architecture index

ADR-002 through ADR-005 respectively decide completion authority, graph
boundaries, SQLite/CAS storage, and host event translation. They cite the
active OpenSpec sections rather than duplicating full implementation details.
This keeps a contributor-facing decision layer while OpenSpec remains the
behavioral contract.

### A deterministic test owns ratification verification

A focused test reads ADR headings and required sections, validates issue #66's
mapping to group 14, confirms the required active spec folders and lifecycle
matrix exist, and asserts that no ADR grants completion authority to hosts,
workers, hooks, or reports. Textual review alone cannot prevent a future
partial ADR set from being treated as complete.

### The existing alpha2 change remains active

This issue adds a narrow implementation change (`ratify-alpha2-runtime-contract`)
without altering the broader `unify-research-runtime-alpha2` planning artifact.
The latter remains in progress until all its delivery groups have evidence.

## Risks / Trade-offs

- [ADR prose drifts from OpenSpec] -> The test resolves explicit references and
  checks the canonical authority terms; future behavior remains governed by the
  Alpha2 capability specs.
- [A documentation PR implies runtime completion] -> Scope and test prohibit
  task-group or release-status promotion.
- [Stale branch material is copied as truth] -> Decisions are revalidated
  against `origin/dev` and the active OpenSpec before inclusion.

## Migration Plan

1. Add ADR-002 through ADR-005 and the focused verifier.
2. Link the authoring README/PRODUCT architecture entry points to the ADR index.
3. Merge to `dev`; dependent implementation issues reference the ratified
   documents but retain their own acceptance evidence.
4. Roll back by reverting this documentation-only PR; no runtime data changes.
