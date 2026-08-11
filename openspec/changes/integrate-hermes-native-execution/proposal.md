## Why

Hermes still persists a private execution checkpoint and can mark research complete from verified batches plus Markdown shape checks. After #57 and #60, that behavior is a split-authority bypass and prevents canonical recovery after provider interruption.

## What Changes

- Translate Hermes delegation, lifecycle, provider failure, retry, and reconciliation observations into the versioned HostEventProtocol.
- Reconstruct active work from the canonical coordinator ledger and mark uncertain attempts unknown before retry.
- Add sanitized provider/model metadata and safe workspace-relative gateway-log references without retaining raw diagnostics.
- Project coordinator actions into replaceable Hermes goal/Kanban records with canonical ids and acceptance criteria.
- **BREAKING** Remove Hermes-local completion/report authority and the writable `.research-tree-hermes/state.json` checkpoint.
- Keep hooks observational and generate Hermes package copies from shared authoring sources.

## Capabilities

### New Capabilities

- `hermes-native-execution`: Canonical Hermes event translation, projection, restart reconciliation, sanitized retry metadata, and non-authoritative hook behavior.

### Modified Capabilities

None.

## Impact

This affects the Hermes execution adapter/runtime hook, HostEvent ingestion boundary, Hermes package generation, group 9 registries and receipts, and focused Hermes/coordinator/package tests. It adds no dependency and does not implement tracing, activation, source capture, workflow orchestration, or adaptive scheduling.
