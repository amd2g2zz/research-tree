<!-- generated from openspec/changes/canonical-lifecycle-facade:PR #371 (#325) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: lifecycle facade reads canonical state
status and verify consume the same canonical state projection; they do NOT echo hard-coded failure lists.

#### Scenario: status surfaces real reasons
- **WHEN** the coordinator reports no unmet obligations
- **THEN** status.ready is true and failure_reasons is empty

#### Scenario: verify returns verdict + reasons
- **WHEN** the canonical completion receipt is missing
- **THEN** verify.status is `verification_pending` and the details dict carries `verdict: "unmet_obligations"` plus the specific reasons; the legacy "verification_pending" shortcut is gone

#### Scenario: doctor splits four sections
- **WHEN** doctor is invoked
- **THEN** the result contains installation, host_capability, run_readiness, completion_verification sections; each independent
