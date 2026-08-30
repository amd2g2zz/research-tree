# Proposal: organizational-operating-model

## Why

issue #330: a technically correct Human Brief is not automatically an
operating model.  Adoption evaluation needs role capacity, owner assignments,
SLA, escalation time, concurrent-project limits, meeting replacement, and
adoption metrics.

## What Changes

NEW `src/research_tree/operating_model.py`:
- `RoleAssignment`: role/owner/capacity/unit (e.g. "research_lead", 2.0 FTE)
- `SLATier`: tier/target_response/escalation_after
- `OperatingModelProjection`: roles, sla, concurrent_project_limit,
  meeting_replacement_per_week, adoption_metrics
- `build_operating_model(...)`: factory; adoption_metrics start at zero
  (never fabricated for fresh deployments)
- `to_dict()`: canonical serialization for the Human Brief

## Impact

- src/research_tree/operating_model.py (new)
- No behavior change to existing modules
- This is the P2 addition to the Human Brief (issue #330); the brief's
  consumer is the existing #268-style narrative generator

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| Capture all required fields | test_operating_model_captures_required_fields |
| Build structured record | test_build_operating_model_yields_structured_record_from_inputs |
| Serialize to dict | test_operating_model_serializes_to_dict |
| Fresh-install zeros (not fabricated) | test_operating_model_carries_zero_defaults_for_initial_deployment |
| Role assignment full serialization | test_role_assignment_serializes_with_all_fields |
