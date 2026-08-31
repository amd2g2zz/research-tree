# Proposal: host-capability-discovery

## Why

issue #322 (confirmed): unknown host terms push work back to the requester.
Pi is unsupported. Capability discovery records available files/shell/retrieval/
persistence/delegation/experiment/structured-input surfaces.

## What Changes

EXTEND `src/research_tree/host_capabilities.py` (already in repo from prior
alpha2 cohort):
- Add `pi` to `HOSTS` and `HOST_SURFACES` (governed compatibility path).
- Tests cover the 7 acceptance criteria: known-host manifest shape,
  fallback recording, host-iteration UI is host-specific, distinct disposition
  states, unknown host ≠ user deflection.

## Impact

- src/research_tree/host_capabilities.py: add Pi to HOSTS/HOST_SURFACES
- No behavior change for codex/claude-code/hermes
- Pi is a known host with recon path; no user deflection

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| Pi has activation/capability probe/setup/lifecycle/status/recovery path | test_pi_in_host_registry_with_native_surface |
| Capability discovery records 7 surfaces | test_capability_manifest_records_each_surface |
| Missing capability → specific degraded strategy | test_missing_capability_yields_degraded_strategy_with_fallback |
| Capability discovery ≠ user deflection for unknown hosts | test_capability_manifest_for_known_host_returns_structured_record + test_unknown_host_recordings_are_structured_not_user_deflection |
| Host-iteration UI is host-specific | test_pi_supported_via_compatibility_path |
