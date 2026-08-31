## 1. Tests (RED first)

- [x] 1.1 RED: 10 doc/fixture tests failed pre-implementation (module absent)
- [x] 1.2 GREEN: 10/10 + 2 coordinator guards + 1 doctor separation = 13/13

## 2. Implementation

- [x] 2.1 host_attempts.py (outcome, classify, eligible gate, whitelist mapping)
- [x] 2.2 coordinator worker_finished guard (attempt_outcome key)
- [x] 2.3 doctor provider_readiness split section
- [x] 2.4 evaluation fixtures (acceptance matrix, 3 hosts)

## 3. Gate

- [ ] 3.1 full suite + all checks → PR fix/issue-326 → dev
