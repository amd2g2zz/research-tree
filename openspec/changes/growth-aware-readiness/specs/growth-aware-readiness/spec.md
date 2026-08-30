<!-- generated from openspec/changes/growth-aware-readiness (issue #318) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: growth-aware-readiness is canonical
The runtime SHALL treat `growth_aware_readiness` as the canonical implementation for issue #318. Legacy alternatives SHALL NOT be supported in production paths.

#### Scenario: types are non-empty
- **WHEN** the module is imported
- **THEN** the documented dataclasses / enums are defined and importable

#### Scenario: regressions are gated
- **WHEN** tests run
- **THEN** the test file `tests/test_growth_aware_readiness.py` exercises all acceptance items

#### Metadata
- **id**: growth_aware_readiness
- **enforced**: true
- **entities**: test_branch_state_validates_non_negative, test_seal_branch_leaves_siblings_open, test_readiness_delta_per_branch
