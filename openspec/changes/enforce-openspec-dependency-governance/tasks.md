## 1. Failing Governance Fixtures

- [x] 1.1 Add focused tests and valid/invalid fixtures for lifecycle states,
  missing evidence, direct/transitive dependency violations, and cycles.
- [x] 1.2 Add focused fixtures for missing task groups, duplicate primary issue
  ownership, capability ownership mismatch, and unavailable evidence.

## 2. Versioned Registry Model

- [x] 2.1 Define versioned schemas and checked-in registries for task
  verification records and issue execution mappings.
- [x] 2.2 Implement strict parsing and semantic validation for registry shape,
  receipt fields, allowed states, and stable references.

## 3. Dependency-Aware Validator

- [x] 3.1 Implement deterministic graph construction, cycle detection, and
  shortest-path diagnostics for direct and transitive dependency failures.
- [x] 3.2 Implement issue/capability/group cross-reference validation and a
  deterministic JSON governance report with a release-ready verdict.
- [x] 3.3 Add a read-only command entry point that exits non-zero for any
  semantic violation and does not mutate planning or runtime state.

## 4. Alpha2 Registry Repair

- [x] 4.1 Extend task execution metadata with groups 23--32 and initialize
  unproven groups as non-verified.
- [x] 4.2 Add authoritative mappings for #71, #72, #73, #80, #82, #83, #84,
  #85, #86, and #87.
- [x] 4.3 Repair delivery-matrix references and remove the #69/#55 and
  #85/#64/#72 dependency cycles while preserving #64/#84 and
  #59/#87/#73/#85 ownership boundaries.

## 5. Integration and Evidence

- [x] 5.1 Integrate governance validation into the Alpha2 release/delivery
  validation path without treating unavailable owned scripts as passing.
- [x] 5.2 Run focused, full, strict OpenSpec, package parity, and diff checks;
  record the exact outputs and update only completed task checkboxes.
- [ ] 5.3 Open one PR for #89 against `dev`, resolve current-head CI and review
  threads, merge, then perform a non-destructive cleanup review.
