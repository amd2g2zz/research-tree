## Why

`validate_insight_digest` still accepts a prior minimal payload whenever it
omits `schema_version`. That bypass lets an unversioned digest enter current
policy and scheduler paths even though current writers produce a complete,
lineage-rich payload.

## What Changes

- **BREAKING**: Accept only the complete current Insight Digest payload from
  the versioned writer; reject every prior/minimal shape at validation and
  scheduler ingress.
- **BREAKING**: Delete the missing-version return path and legacy-required
  payload contract without an adapter, alias, tolerant default, read
  projection, migration, or user-data operation.
- Align active Insight Digest schemas, examples, and requirements with the
  canonical rich payload rather than publishing the prior minimal schema.
- Register Alpha2 group 60 / issue #174 as a planned current-only retirement
  slice before source verification.

## Capabilities

### New Capabilities

- `current-insight-payload-reader`: Accept exactly one complete,
  versioned Insight Digest payload at current runtime boundaries.

### Modified Capabilities

- `insight-synthesis`: Insight Digest validation requires the canonical rich
  field set and rejects older payload shapes before they can feed policy,
  replay, or delivery.

## Impact

This changes `src/research_tree/insights.py`, current scheduler validation,
focused insight tests, active Alpha2 schemas/examples and registries, plus an
issue-local OpenSpec change. It adds no dependency, does not read or mutate
user-owned data, and does not recreate a compatibility path.
