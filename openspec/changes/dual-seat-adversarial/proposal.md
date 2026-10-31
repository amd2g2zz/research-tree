# dual-seat-adversarial

## Why

Issue #564 (T2 row 2, docs 01 A4 对抗搜索): make-or-break claims get dual-seat evidence — plaintiff seeks only counter-evidence, defense only support; equal budgets; EVSI settles independently per seat; **attack goes first** (先攻后守). Non-mob claims stay single-seat (#558 quota).

## What changes

- `verification/dual_seat.ts`: DualSeatEngine —
  - `shouldRunDualSeat`: only make-or-break claims (cost control — the risk-register mitigation);
  - `runDualSeat`: attack-first ordering, equal budgets per seat, independent EVSI settlement, posterior shift (direction + counter-evidence discovery rate);
  - every seat report is a `provider.action` engine fact.

## impact_scope

- `rt-core/src/verification/dual_seat.ts` (new)
- tests: `rt-core/test/dual_seat.test.ts`
