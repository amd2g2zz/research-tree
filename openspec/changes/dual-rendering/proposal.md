# dual-rendering

## Why

Issue #560 (T1 row 6, docs 01 A6 + 03 §报告与底稿): 渲染是纯函数 — both projections derive from ONE snapshot and can never contradict. The report is the narrative (7 sections); the 底稿 is the structure rendering = downstream interface (schema v1, frozen).

## What changes

- `rendering/dual.ts`:
  - **renderReport** (narrative, 7 sections): restatement / method transparency / claim-ledger by weight / counter-evidence & concessions / qualitative confidence (no fake percentages) / cheapest next step / three-part verdict; deleted nodes disclosed as an audit appendix;
  - **renderDeliverable** (底稿 schema v1 frozen): clarified_question / supported_claims (≥0.9 posterior only) / unverified_assumptions / refuted_and_disposition / capability_outline / constraints (hard vs guessed); deleted_nodes_disclosed;
  - verdict from the closed A6 vocabulary; confidence qualitative bands only;
  - red lines: counter-evidence section always present; unverified_assumptions always present; single-source never plain "supported".
- Same-source: the report and 底稿 are pure functions of the same snapshot — contradiction is structurally impossible.

## impact_scope

- `rt-core/src/rendering/dual.ts` (new)
- tests: `rt-core/test/dual_rendering.test.ts`
