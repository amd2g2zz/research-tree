# early-termination-variant-search

## Why

Issue #563 (T2 row 1, docs 01 A5): the fail-closed gate exists since T0 (#551 PAUSE primitive); this issue adds **kill-graph variant search** ({relax | replace | bypass} the refuted claim → does the DAG still stand?) and the three-choice inquiry UX (埋了 / 继续挖 / 换变体 — the question is not the verdict). H5: budget savings ≥50%.

## What changes

- `termination/variant_search.ts`: VariantSearchEngine —
  - **searchVariants**: mechanical (kill-graph topology, not LLM-judged); only DAG-standing variants survive;
  - **buildInquiry**: evidence + standing variants, choices [bury, continue, switch-variant], NO verdict in the inquiry;
  - **resolveBury**: NO-GO recommendation (is_final=false — verdict at freeze);
  - **recordSavings**: H5 ratio (≥50% threshold) vs the full-run estimate.
- Early-termination hard gate + PAUSE primitive already shipped in #551.

## impact_scope

- `rt-core/src/termination/variant_search.ts` (new)
- tests: `rt-core/test/variant_search.test.ts`
