# Add Resolvable Evidence Artifacts

Issue #54 establishes immutable, multimodal evidence artifacts and typed anchors
that can be resolved to exact CAS content. This change is limited to artifact
metadata, selectors, provenance grouping, and Finding Pack integration. Oracle
execution and closure remain separate Alpha2 work.

## Why

String URLs and file references are not sufficient to prove that a claim still
refers to the bytes, revision, or image region that was inspected.

## Outcome

Consequential observations can carry an `EvidenceAnchor` and are rejected when
the referenced artifact is missing, changed, inactive, or outside the workspace.
