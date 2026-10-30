# a0-decomposition

## Why

Issue #549 (T0 row 4, docs 01 A0): after the user confirms in chat, the conversation is decomposed into six element classes; the confirmed set ships with v0 as the constitution of the research. Extraction is model-side; schema/provenance/checklist validation is engine-side (two-layer contract #501).

## What changes

- `decomposition/engine.ts`:
  - **溯源律 (provenance law)**: every element carries source (chat-message/attachment id + quote); unsourceable elements are hallucinations — **dropped before persist**, not rejected;
  - **sufficiency checklist (mechanical)**: six classes ≥1 (refusals may be explicitly "none" via confirmation note), difficulty without kill-candidate mapping = pre-registration gap;
  - **confirm vs draft split**: 确认 is gated (gaps block with named gaps); incomplete sets persist as draft (保存草稿);
  - **semantic classification**: one utterance splits into several classes; constraints separate hard (deployment fact) from guessed;
  - persistence via the #547 decompositions table (confirmed sets are the constitution; re-confirm = major pivot rejected).
- Relation to A1: A1's four-way routing (T1 #555) is per-utterance online routing; A0 is batch structuring after convergence.

## impact_scope

- `rt-core/src/decomposition/engine.ts` (new)
- tests: `rt-core/test/decomposition.test.ts`
