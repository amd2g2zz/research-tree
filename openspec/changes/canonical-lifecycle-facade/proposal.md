# Proposal: canonical-lifecycle-facade

## Why

issue #325: `research-tree status/verify/doctor` were a preparation shell.
`_runtime_readiness` returned a fixed failure list; `_verify` always set
`verification_pending`; `doctor` collapsed installation + provider + run + completion
into one boolean. The released test treated permanent pending as success.

## What Changes

1. `cli._runtime_readiness`: drops the hard-coded fake failure list; reads
   `coordinator.why_not_complete(run_id)` for real canonical unmet obligations;
   surfaces static project-workspace checks separately.  Returns real `ready`.
2. `cli._verify`: validates canonical completion receipt; produces field-level
   reasons (`verdict`, `reasons`, `package_id`, `host_id`, `revision`) and a
   real status (`verified` | `verification_pending` with reasons |
   `verification_failed` with reasons).  No more legacy "verification_pending"
   shortcut.
3. `cli._doctor`: 4-section split — `installation` (hosts + state) /
   `host_capability` (provider readiness, #326) / `run_readiness` (real canonical
   reasons) / `completion_verification` (state with verify note).  Each
   section independent; aggregate is honest.
4. tests/test_lifecycle_facade_canonical.py: 5 tests covering the contract.

## Impact

- src/research_tree/cli.py: 3 functions wired
- No behavior change for callers that didn't depend on the legacy fake reasons

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| status/verify 读 canonical, 不再 fake | test_status_projects_canonical_revision_and_unmet_obligations |
| verify 字段级 reason, 不再 verification_pending shortcut | test_verify_returns_specific_field_level_reasons_not_legacy_string |
| doctor 4 段分离 | test_doctor_4_section_split_declared_in_source |
| run identity 仍暴露 (revision) | test_status_surfaces_run_id_and_revision_even_for_empty_runs |
| 缺 verify path 不再是 pending | test_verify_no_legacy_verification_pending_shortcut |
