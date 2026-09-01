## Why

Tracked evaluation definitions, untracked transcripts, baselines, reviews, and
generated runs currently lack an enforced lifecycle boundary. Alpha2 release
evidence cannot be reproduced or audited until these assets use one canonical
namespace with machine-checked provenance and leakage rules.

## What Changes

- Ratify `evaluation/` as the only source namespace and retire `evals/`.
- Define non-overlapping tracked and disposable asset classes with schemas,
  identifiers, provenance, redaction, retention, and size policies.
- Add a deterministic validator for schema drift, misplaced output, dangling
  provenance, hidden-oracle leakage, and oversized transcripts.
- Preserve the public case manifest compatibility path and provide a
  clean-checkout public baseline entrypoint.
- Inventory user-owned legacy experiences without deleting or auto-migrating
  them.

## Capabilities

### New Capabilities

- `evaluation-asset-governance`: Canonical paths, lifecycle contracts, schemas,
  validation, and deterministic entrypoints for evaluation assets.

### Modified Capabilities

None.

## Impact

This adds evaluation schemas/source directories, governance tooling and tests,
updates path registry documentation, and records the Alpha2 group-20 receipt.
It does not publish hidden oracles or modify untracked local evaluation data.
