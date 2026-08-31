## 1. Tests (RED first)

- [x] 1.1 RED: 9 freshness + 2 intake tests failed pre-implementation
- [x] 1.2 GREEN: 11/11

## 2. Implementation

- [x] 2.1 freshness.py (policy, record, assess, from_dict whitelist)
- [x] 2.2 RepositoryInspector accepts optional freshness_policy
- [x] 2.3 inspect payload carries freshness record when policy present
- [x] 2.4 prefix-overlap for relevant_paths matching

## 3. Gate

- [ ] 3.1 full suite + all checks → PR fix/issue-327 → dev
