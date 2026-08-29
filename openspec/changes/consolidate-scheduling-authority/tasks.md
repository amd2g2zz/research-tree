## 1. Tests (RED first)

- [x] 1.1 RED: 4 tests failed pre-implementation (export present; no lineage field; no policy arg)
- [x] 1.2 GREEN: 4/4 + worker-orchestration 3/3 (wave semantics intact)

## 2. Implementation

- [x] 2.1 coordinator: policy= ctor arg; _policy_proposal_id helper at dispatch decision point
- [x] 2.2 orchestration.py deleted; exports removed; zero repo residue
- [x] 2.3 ADR-006 written (mapping, alternatives, rollback)

## 3. Gate

- [ ] 3.1 full suite + all checks → PR refactor/issue-333 → dev (rebased on #332's f553aaf)
