# evsi-actions

## Why

Issue #557 (T1 row 3, docs 01 A3): "再读一篇论文还是跑五分钟 benchmark" is decided by ONE formula — EVSI/cost. Candidate actions scored uniformly; make-or-break claims always go first; every selection is replayable (candidates, scores, chosen, hindsight regret).

## What changes

- `evsi/selector.ts`: selectAction — EVSI/cost ranking with make-or-break priority pool; zero-cost candidates raise (degenerate winners guarded); replay disclosure (candidates + chosen + hindsight_best).
- The EVSI estimation is a pluggable scorer (mock-e2e harness injects one; the real estimator lands with evidence-engine calibration). Experiment tier-k actions slotted, gated off until #567.

## impact_scope

- `rt-core/src/evsi/selector.ts` (new)
- tests: `rt-core/test/evsi.test.ts`
