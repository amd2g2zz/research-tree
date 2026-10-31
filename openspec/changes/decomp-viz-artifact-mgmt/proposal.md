# decomp-viz-artifact-mgmt

## Why

Issue #561 (T1 row 7, docs 03 §六要素分解可视化): grouped card wall, six grids, 溯源律 visible on every card, edit rights before confirm, insufficient elements show "待对齐" placeholders (never demo content), checklist gates confirm; artifact management & freeze-commit UI post-convergence.

## What changes

- `ux/card_wall.ts`: CardWallModel — six P3 classes only (claims_preview excluded — it is the ledger preview, not a card group); cards carry provenance ("来自你的话" / "来自附件"); deleteElement mutates the draft model (edit rights before confirm); placeholderFor names the gap (非演示脚手架); confirm delegates to the #549 engine (checklist-gated). renderCardWall renders the text projection the P3 page displays.

## impact_scope

- `rt-core/src/ux/card_wall.ts` (new)
- tests: `rt-core/test/card_wall.test.ts`
