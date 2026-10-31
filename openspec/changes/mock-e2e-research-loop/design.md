# design — mock-e2e-research-loop

The loop harness composes production pieces (no test doubles for the engine):
the scheduler's ready-set cut → pi-subagents dispatch (fake API) → the
"worker" applies verdicts through `EngineCore.upsertClaim` (dual-write) →
open-loop check AFTER the worker pass → ROLLUP. The A2 projection rule
(≥0.9 decided / ≤0.1 refuted) maps posteriors to lifecycle states; belief
propagation reopens descendants append-only; resume-continue reopens the
affected stage for re-verification.

## impact_scope

As proposal. GitNexus: test-only + one pinned semantic fix.

## rejected_designs

- Real LLM/CLI calls (that is the #554/pi-host territory; this file mocks).
- The loop as a src module now (the production loop is #552's pi extension +
  #551 machine; the harness pins the integration contract until then).
- Budget-exhausted as the PARK trigger in e2e (worker failure → retry→park
  is the #550 semantics; budget-exhausted is unit-covered).
