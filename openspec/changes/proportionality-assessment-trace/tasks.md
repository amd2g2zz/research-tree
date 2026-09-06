## 1. Tests (RED first)

- [x] 1.1 RED: registry carries the seven-entry contract; duplicate
      registration still rejected; verify_traces checks the four fields'
      presence; proposal-shaped derivations include the assessment;
      misunderstood-intent derivations do not

## 2. Implementation

- [x] 2.1 registry append (`proportionality_assessment`, four required fields)
- [x] 2.2 `_gap_required_traces` proposal branches extended
- [x] 2.3 craft-doc note + regenerated packages (generated-only)
- [x] 2.4 six-type pins updated to the seven-type contract

## 3. Gate

- [ ] 3.1 full suite + ruff + validate + governance + parity → PR (stacked on
      feat/issue-493-turn-shape-gate, rebased onto dev at push time)
