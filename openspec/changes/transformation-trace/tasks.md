## 1. Tests (RED first)

- [x] 1.1 RED: registry carries digest-first + viewpoint-hints; verify_traces
      checks their fields; missing alternatives rejected
- [x] 1.2 RED: pack compile validates {ratio} presence+range and persists it

## 2. Implementation

- [x] 2.1 registry append (two types, nine total)
- [x] 2.2 ledger `_normalize_transformation` + compile parameter + payload
- [x] 2.3 nine-type pin in test_turn_contract.py

## 3. Gate

- [ ] 3.1 full suite + ruff + validate + governance + parity → PR (stacked on
      feat/issue-498-proportionality-trace)
