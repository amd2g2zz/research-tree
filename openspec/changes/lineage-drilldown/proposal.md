# lineage-drilldown

## Why

Issue #566 (T2 row 4, docs 02 §递归阶段化): Flink-style UI lineage walk — from any conclusion node, ≤3 clicks reach raw evidence. The rule holds for every historical version (snapshots preserve their own evidence references — A7). No streaming framework (克制清单).

## What changes

- `canvas/lineage.ts`: LineageDrillDown — resolves the ≤3-click path mechanically from the version store: canvas node (select claim) → detail drawer (claim/posterior/tier) → raw evidence (sha256-referenced source). Unknown claims return null (no fake lineage).

## impact_scope

- `rt-core/src/canvas/lineage.ts` (new)
- tests: `rt-core/test/lineage.test.ts`
