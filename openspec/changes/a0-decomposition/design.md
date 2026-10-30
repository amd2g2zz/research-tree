# design — a0-decomposition

Pure functions over the #547 decompositions surface (no new tables):
`parseDecomposition` (provenance filter, six-class keyed), `checklistFor`
(computed, never LLM-judged), `saveDraftDecomposition` (incomplete allowed),
`confirmDecomposition` (checklist-gated; re-confirm rejected as major pivot).

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Rejecting unsourceable elements with an error (they are extractor guesses —
  dropping is the documented 溯源律 behavior; the drop count is recorded in
  checklist_state).
- LLM-judged sufficiency (the checklist is computed — 机械规则).
- Confirming with gaps (the UI blocks; the engine enforces).
- Confirmed-set mutation (re-sign flow is the state machine's, #551).
