# design — decomp-viz-artifact-mgmt

CardWallModel wraps the #549 ParsedDecomposition: cards() scopes to the six
P3 classes (claims_preview excluded — it renders in the claims preview
section), provenance formatting (chat-message vs attachment), placeholderFor
for empty classes (待对齐 — non-demo scaffolding red line), confirm gated by
the #549 checklist.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Demo-content placeholders (red line: 非演示脚手架 — the placeholder names
  the gap).
- Mutation after confirm (post-confirmation change is a major pivot — #549
  rejects re-confirmation).
- Claims_preview as a card group (it renders in the preview section, not the
  wall).
