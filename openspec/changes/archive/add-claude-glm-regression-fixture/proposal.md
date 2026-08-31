## Why

Issue #72 requires a regression fixture for alignment, correction, research
continuity, delivery, and attribution boundaries. The original source session
is not retained with sufficient provenance for historical reproduction, so this
change must not fabricate a transcript or assign causation to GLM5.2.

## What Changes

- Add a governed public case that is explicitly synthetic and non-historical.
- Add a deterministic runner that checks activation ordering, one open question,
  correction invalidation, task identity, recursive continuation, attribution
  boundaries, and evidence-bound dual delivery.
- Record missing GLM5.2 access as a named unavailable blocker that cannot pass
  parity or causal-attribution checks.
- Extend local receipt output to the existing ignored evaluation-run boundary
  for this evaluation-owned task group.

## Capabilities

### New Capabilities

- `claude-glm-regression-fixture`: Public synthetic regression controls with
  honest runtime-comparison limitations.

### Modified Capabilities

- `evaluation-asset-governance`: Register the deterministic Issue #72 runner
  without changing the public asset or hidden-oracle boundary.

## Impact

The change adds governed evaluation source assets, a self-contained harness,
focused tests, an Issue #72 OpenSpec change, and group-24 evidence wiring. It
does not modify coordinator behavior, invoke provider runtimes, retain raw
sessions, or claim historical transcript reproduction or GLM causation.
