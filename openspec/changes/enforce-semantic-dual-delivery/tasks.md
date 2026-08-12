## 1. Contract and red tests

- [x] 1.1 Extend the versioned DeliveryManifest and DeliveryAcceptance schemas and examples for exact pair binding, claim lineage, depth assessment, and typed outcomes.
- [x] 1.2 Add failing semantic-delivery tests for legacy kinds, manifest drift, orphan claims, missing boundaries, unresolved P0 decisions, shallow reasoning, and non-semantic filler.
- [x] 1.3 Add failing acceptance lifecycle tests for stale/generic acceptance, partial/rejected outcomes, correction routing, and withdrawal.
- [x] 1.4 Add a failing compatibility/compiler test proving new writes use Human Research Report while legacy aliases remain readable.

## 2. Semantic delivery implementation

- [x] 2.1 Implement typed manifest, claim-index, output-digest, depth-rubric, and professional human-report validation without size or heading heuristics.
- [x] 2.2 Implement exact-pair DeliveryAcceptance with contextual feedback classification and deterministic lifecycle routing.
- [x] 2.3 Update the compiler to emit the canonical Human Research Report kind and field while retaining explicit read compatibility aliases.
- [x] 2.4 Preserve validate-before-write and atomic batch behavior, including stale-revision replay safety.

## 3. Governance and verification

- [x] 3.1 Update umbrella semantic-delivery requirements, schemas, examples, and design decisions to match the implemented contract.
- [x] 3.2 Run focused tests and capture red-to-green evidence.
- [x] 3.3 Run Ruff, the full pytest suite, strict local and umbrella OpenSpec validation, package reproducibility, governance checks, and `git diff --check`.
