## Context

The umbrella registry already names `evaluation/` as canonical and
`.research-tree/evaluation-runs/` as disposable, but only three case files are
tracked and no checker enforces the declared directory contract. Large local
experience artifacts are user-owned inputs and cannot be scanned, moved, or
deleted by this change.

## Goals / Non-Goals

**Goals:**

- Make the registry executable without adding a runtime dependency.
- Validate tracked source assets from a clean checkout and classify local
  legacy paths without reading their contents.
- Keep hidden oracle bodies outside worker-visible and tracked public fixtures.
- Produce deterministic diagnostics and a source-bound group-20 receipt.

**Non-Goals:**

- Running #64 release evaluation, publishing private oracles, or auto-migrating
  local transcripts and experiences.

## Decisions

1. The standard-library checker reads the canonical registry and JSON assets,
   using explicit schema-shaped validation rather than adding `jsonschema`.
2. Tracked evaluation classes occupy fixed non-overlapping prefixes. Raw runs
   are valid only under the ignored disposable root; `evals/` is forbidden.
3. Public oracle references are opaque identifiers only. Keys or values that
   expose oracle bodies, expected patches, secrets, or private transcripts fail.
4. Provenance-bearing assets use immutable stable IDs and digest/source refs;
   referential integrity is checked across the inventory in one pass.
5. User-owned legacy paths are reported as migration candidates by path only.
   The checker never deletes, moves, truncates, or stages them.

## Risks / Trade-offs

- [A conservative leakage detector can flag benign fixture text] -> restrict
  detection to governed keys and explicit marker patterns with regression tests.
- [A custom validator covers less than a general schema engine] -> version the
  schemas and test every governed class and failure code directly.
- [Tracked results can grow] -> enforce per-class byte limits and require
  redacted provenance-complete summaries rather than raw transcripts.

## Migration Plan

Add canonical directories, schemas, safe seed fixtures, checker, tests, and
documentation. Keep the compatibility case manifest at its current path. Do not
create or remove local experience/evals material. Rollback removes only these
tracked additions and returns group 20 to planned.

## Open Questions

None for this issue; release-specific retention durations remain owned by #64.
