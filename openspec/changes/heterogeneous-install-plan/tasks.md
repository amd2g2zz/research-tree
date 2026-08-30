## 1. Tests (RED first)

- [x] 1.1 RED: 5/9 tests failed pre-implementation (module API missing)
- [x] 1.2 GREEN: 9/9

## 2. Implementation

- [x] 2.1 plan_heterogeneous_install: per-host plan, skip not raise
- [x] 2.2 installation_status_per_host: per-host + aggregate
- [x] 2.3 hermes_external_dirs_snippet: idempotent, preserves unrelated
- [x] 2.4 per-host plan covers mixed scope / conflict / rollback / unavailable home / repeated

## 3. Gate

- [ ] 3.1 full suite + all checks → PR fix/issue-328 → dev
