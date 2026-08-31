<!-- generated from openspec/changes/introduce-problem-forest (issue #314) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: introduce-problem-forest is canonical
The runtime SHALL treat `introduce_problem_forest` as the canonical implementation for issue #314. Legacy alternatives SHALL NOT be supported in production paths.

#### Scenario: types are non-empty
- **WHEN** the module is imported
- **THEN** the documented dataclasses / enums are defined and importable

#### Scenario: regressions are gated
- **WHEN** tests run
- **THEN** the test file `tests/test_introduce_problem_forest.py` exercises all acceptance items

#### Metadata
- **id**: introduce_problem_forest
- **enforced**: true
- **entities**: test_forest_space_has_5_values, test_reconciliation_kind_has_8_values, test_forest_mutation_preserves_invariants
