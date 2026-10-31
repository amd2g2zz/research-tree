# design — a1-dialogue-controller

Pure controller over the #547 surface (claims/hypotheses rows) — no new
tables. The model side (pi loop) classifies utterances; the engine routes by
declared kind and enforces the mechanical rules. Divergence check compares
parking-lot volume vs claim volume.

## impact_scope

- `rt-core/src/dialogue/controller.ts` (new)
- tests: `rt-core/test/dialogue.test.ts`

## rejected_designs

- LLM-based routing inside the engine (two-layer contract).
- A privileged correction channel (corrections route identically).
- Felt convergence (C1-C5 computed).
