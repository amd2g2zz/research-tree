## Why

`OpenSpecExporter` is a RunStore-only runtime boundary that reads a persisted
Technical Research Package and writes an OpenSpec change into a caller-supplied
directory. It is not part of the current canonical runtime, and no canonical
replacement has been selected. Retaining an opt-in exporter would keep a
retired RunStore authoring path alive.

## What Changes

- **BREAKING**: Delete `research_tree.openspec` and the root-package
  `OpenSpecExporter`, `OpenSpecExport`, `OpenSpecExportError`, and
  `InvalidOpenSpecExportError` exports.
- Delete the dedicated legacy exporter suite and its E2E-only RunStore/Finding
  Pack consumer instead of migrating either to a new writer.
- Remove active product, operational, reference, registry, and generated
  package claims for the exporter. Historical `docs/specs/` and `docs/reviews/`
  records and source-bound group receipts remain audit material only.
- Register Alpha2 group 82 / issue #176 as the planned source-removal slice
  after verified group 81 / issue #171.

## Capabilities

### New Capabilities

- `runstore-openspec-export-removal`: Retire the RunStore-only OpenSpec export
  boundary without a replacement exporter, bridge, alias, compatibility
  reader, migration, fallback, dual state, or user-data operation.

## Impact

This removes `src/research_tree/openspec.py`, its root exports, dedicated
legacy behavior tests, the E2E import consumer, and current authority claims.
It preserves `tests/test_assurance_adapters.py` and its reserved legacy
fixture for #165. The removal preserves historical receipt commands only when
their entrypoints existed at a receipt source revision reachable from the
current revision. It neither reads, writes, moves, nor deletes user-owned
RunStore or OpenSpec data; rollback is a Git revert.
