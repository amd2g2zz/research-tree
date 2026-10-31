# design — dual-rendering

Pure functions (snapshot, ctx) → projections. The ledger narrative lists ALL
claims by weight (transparency); the 底稿's supported_claims projection
applies the promotion threshold (≥0.9). Unverified claims surface as
unverified_assumptions (downstream must read before starting). Constraints
split hard/guessed. Verdicts map to the closed A6 vocabulary.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Two separate snapshot reads (contradiction becomes possible — one source).
- Numeric confidence (假百分比 banned).
- Hiding the ledger's minor/unverified claims from the report (transparency
  red line: the ledger narrative lists everything with posteriors).
- LLM in the rendering path (pure functions — the narrative text is
  template-derived; the LLM narrative lands in the pi loop above this layer).
