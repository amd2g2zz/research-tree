# Proposal: heterogeneous-install-plan

## Why

issue #328 (confirmed): `research-tree install --host all --scope project`
applies one scope to all hosts. Hermes deliberately uses skills.external_dirs,
so target resolution RAISES before any per-host plan exists — the dry run
exits as invalid even though codex/claude have valid project paths.  The fix:
plan all hosts first; unsupported combinations become plan entries (skipped
+ reason + required_config snippet), not exceptions.

## What Changes

1. `plan_heterogeneous_install` (skill_setup.py): returns one plan with
   `entries` (per host: action=install|skipped|current|conflict, target,
   package, skill_source, discovery, rollback_boundary, required_config,
   reason) and `aggregate_ready` (does not hide partial readiness).
2. `installation_status_per_host`: per-host dict + aggregate.
3. `hermes_external_dirs_snippet`: machine-readable, idempotent YAML fragment
   for skills.external_dirs; preserves unrelated keys; never overwrites.
4. tests/test_heterogeneous_install_plan.py: 9 tests covering all
   acceptance lines.

## Impact

- src/research_tree/skill_setup.py: 3 new functions, no breaking changes
- Tests use tmp_path homes; no Docker needed
