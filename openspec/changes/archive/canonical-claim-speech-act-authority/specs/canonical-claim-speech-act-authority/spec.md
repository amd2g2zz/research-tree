<!-- generated from openspec/changes/canonical-claim-speech-act-authority (issue #316) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: canonical-claim-speech-act-authority is canonical
The runtime SHALL treat `canonical_claim_speech_act_authority` as the canonical implementation for issue #316. Legacy alternatives SHALL NOT be supported in production paths.

#### Scenario: types are non-empty
- **WHEN** the module is imported
- **THEN** the documented dataclasses / enums are defined and importable

#### Scenario: regressions are gated
- **WHEN** tests run
- **THEN** the test file `tests/test_canonical_claim_speech_act_authority.py` exercises all acceptance items

#### Metadata
- **id**: canonical_claim_speech_act_authority
- **enforced**: true
- **entities**: test_assertion_with_basis_becomes_candidate, test_unknown_belief_status_raises, test_legacy_disputed_maps_to_contested
