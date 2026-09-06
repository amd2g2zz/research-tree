## 1. Tests (RED first)

- [x] 1.1 RED: compliant shape recorded (schema 2); over-long flagged naming
      `length`; decision/question caps mechanical; ratio slot carried
- [x] 1.2 RED: legacy schema 1 records read; field mismatch rejected;
      receipt carries `last_turn_shape`; verdict-vs-violations consistency

## 2. Implementation

- [x] 2.1 `measure_turn_shape` + named constants + `_validate_turn_shape`
- [x] 2.2 record schema 2 (optional `turn_shape`, legacy read), append
      parameter, receipt `last_turn_shape`
- [x] 2.3 #497 receipt/schema assertions extended for the additive key

## 3. Gate

- [ ] 3.1 full suite + ruff + validate + governance + parity → PR
      feat/issue-493-turn-shape-gate → dev
