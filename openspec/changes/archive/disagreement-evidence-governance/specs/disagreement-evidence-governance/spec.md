<!-- generated from openspec/changes/disagreement-evidence-governance (issue #317) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: disagreement-evidence-governance is canonical
The runtime SHALL treat `disagreement_evidence_governance` as the canonical implementation for issue #317. Legacy alternatives SHALL NOT be supported in production paths.

#### Scenario: types are non-empty
- **WHEN** the module is imported
- **THEN** the documented dataclasses / enums are defined and importable

#### Scenario: regressions are gated
- **WHEN** tests run
- **THEN** the test file `tests/test_disagreement_evidence_governance.py` exercises all acceptance items

#### Metadata
- **id**: disagreement_evidence_governance
- **enforced**: true
- **entities**: test_pressure_precedence_table_order, test_evaluate_dispute_raises_on_unknown_signal, test_pressure_ledger_append_only
