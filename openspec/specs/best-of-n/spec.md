<!-- generated from openspec/changes/best-of-n:PR #370 (#334) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: high-impact decisions compare candidates
A P0 Decision Slot closed by a single candidate without a recorded single-candidate degradation is a closure violation. The closure payload must persist candidate generation, scoring rubric, and selection rationale.

#### Scenario: single candidate on a P0 slot
- **WHEN** close_p0_slot_with_single_candidate is called with one candidate and degradation_recorded=False
- **THEN** it raises a single_candidate error

#### Scenario: explicit degradation unlocks single candidate
- **WHEN** close_p0_slot_with_single_candidate is called with one candidate and degradation_recorded=True
- **THEN** the slot closes and the result carries degradation_recorded=True

#### Scenario: method independence
- **WHEN** the pool is built with require_method_independence=True and two candidates share the same method
- **THEN** the pool raises an independence error
