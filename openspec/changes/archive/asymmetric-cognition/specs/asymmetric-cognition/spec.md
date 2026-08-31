<!-- generated from openspec/changes/asymmetric-cognition (issue #315) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: asymmetric-cognition is canonical
The runtime SHALL treat `asymmetric_cognition` as the canonical implementation for issue #315. Legacy alternatives SHALL NOT be supported in production paths.

#### Scenario: types are non-empty
- **WHEN** the module is imported
- **THEN** the documented dataclasses / enums are defined and importable

#### Scenario: regressions are gated
- **WHEN** tests run
- **THEN** the test file `tests/test_asymmetric_cognition.py` exercises all acceptance items

#### Metadata
- **id**: asymmetric_cognition
- **enforced**: true
- **entities**: test_compute_alignment_returns_per_branch_dict, test_per_branch_zero_coverage_returns_zero, test_catch_up_triggers_identifies_gaps
