## Why

`StrategyProjection` still accepts a prior serialized shape that omits
`preference_influences`, even though the current writer and canonical schema
require the complete field. That reader-side default inference preserves a
retired payload contract and lets a non-canonical digest shape enter current
runtime state.

## What Changes

- **BREAKING**: Require `preference_influences` in every
  `StrategyProjection.create` call and serialized projection payload.
- **BREAKING**: Delete the prior-shape parser branch, inferred empty tuple,
  alternate digest calculation, and legacy-read regression coverage.
- Archive the completed preference-profile OpenSpec change that actively
  mandates legacy projection reads, retaining its tasks and evidence as
  historical audit material.
- Register Alpha2 group 59 / issue #173 as a planned current-only reader
  retirement slice before source changes are verified.

## Capabilities

### New Capabilities

- `current-strategy-projection-reader`: Accept only the complete canonical
  strategy projection payload without aliases, defaults, coercion, migration,
  or a read projection.

### Modified Capabilities

- `strategy-handoff`: Strategy projection creation and loading require the
  current canonical field set, including preference influence lineage.

## Impact

This changes `src/research_tree/strategy_projection.py`, every direct current
projection writer fixture, focused strategy tests, active Alpha2 registries,
and the completed preference-profile OpenSpec location. It adds no dependency,
does not inspect or mutate user-owned data, and does not add a replacement
reader or migration path.
