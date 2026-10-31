# evidence-engine-lite

## Why

Issue #556 (T1 row 2, docs 01 贝叶斯证据引擎 L1): the lite layer that already de-ranks conflicting sources — full L1 (earned posteriors, incentive vectors, astroturfing) lands with calibration.

## What changes

- `evidence/engine.ts`: EvidenceEngine —
  - **source registry** with provenance (origins.py promoted to reasoning input; #547 sources table persistence);
  - **weighted-vote point estimate**: reliability-weighted verdicts (lite stand-in for the earned posterior);
  - **independence collapse**: sources citing other listed sources collapse to the independent root (citation chains are one piece of evidence);
  - **quick-check layer**: new verdicts × evidence index — inline conflict flags at extraction time (A1 pipeline slot);
  - **conflict index** per claim.
- Incentive vectors / astroturfing: schema-ready fields only (behavior with calibration, T4).

## impact_scope

- `rt-core/src/evidence/engine.ts` (new)
- tests: `rt-core/test/evidence.test.ts`
