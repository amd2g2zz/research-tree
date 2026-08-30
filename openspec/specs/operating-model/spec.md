<!-- generated from openspec/changes/organizational-operating-model:PR #380 (#330) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: Human Brief carries an organizational operating model
The Human Brief's organizational operating model records role capacity, owner assignments, SLA, escalation time, concurrent-project limits, meeting replacement, and adoption metrics.

#### Scenario: fresh installation uses zero adoption metrics
- **WHEN** the operating model is built for a new deployment (no runs yet)
- **THEN** adoption_metrics contains explicit zero values, never fabricated non-zero values

#### Scenario: serialization is canonical
- **WHEN** the operating model is serialized
- **THEN** the dict carries roles (list of role/owner/capacity/unit), sla, concurrent_project_limit, meeting_replacement_per_week, adoption_metrics
