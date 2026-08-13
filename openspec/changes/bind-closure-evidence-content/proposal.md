## Why

The closure assessor currently accepts caller-selected Finding Packs and only
checks their artifact lineage. A graph can therefore have valid-looking
identifiers while its captures or evidence were never durably bound to CAS
content, or while a caller omits a current contradictory Finding from a
decision.

## What Changes

- Require closure evidence to resolve through exact, current SourceCapture,
  AcquisitionReceipt, EvidenceArtifact, and origin relationships with matching
  durable content bindings.
- Derive the current decision-bound Finding set and reject an assessment whose
  supplied Findings do not match it exactly.
- Register Alpha2 group 46 / GitHub issue #160 as a planned, independently
  verifiable child slice.
- Preserve the current `SlotClosureAssessor.assess()` call shape for the
  follow-on quality and token-currentness slice.

## Capabilities

### New Capabilities

- `closure-evidence-content-binding`: Conservative closure evidence admission
  based on canonical content and the complete current Finding set.

### Modified Capabilities

- None.

## Impact

This change affects `research_tree.closure`, its focused closure tests, and the
Alpha2 execution, verification, issue, delivery, and umbrella task registries.
It adds no dependency, public CLI surface, completion admission, quality
scoring, or closure-token currentness behavior.
