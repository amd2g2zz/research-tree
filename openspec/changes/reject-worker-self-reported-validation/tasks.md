## 1. Contract and tracker

- [x] 1.1 Validate the proposal, design, and worker-validation-trust spec in strict OpenSpec mode.
- [x] 1.2 Reconcile #106 and #112 tracker dependencies so #109 is recorded as an independent legacy guard and not as canonical OracleRun completion.

## 2. Red tests

- [x] 2.1 Replace the worker-pass delivery test with assertions that the slot stays open, the pass is untrusted, and delivery finalization is rejected.
- [x] 2.2 Add distinct-finding repeated-pass coverage proving one active verifier-needed continuation, fresh-attempt accounting, and replacement after a completed continuation.
- [x] 2.3 Add existing-authority preservation, failed-retry compatibility, missing/non-mapping/malformed no-op, baseline-ingestion, unrelated-frontier coexistence, running-node, and identity-collision tests.

## 3. Runtime boundary

- [x] 3.1 Stop worker validation ingestion from mutating authoritative `validation_passed`.
- [x] 3.2 Record recognized worker statuses, map `passed` to `reported_passed_untrusted`, and create a stable mandatory verifier-needed validation continuation epoch with a protocol-owned identity namespace.
- [x] 3.3 Ignore malformed validation mappings without changing attempt or closure state while retaining failed/inconclusive behavior.

## 4. Verification and delivery

- [x] 4.1 Run focused recursive-search tests and the complete regression suite.
- [x] 4.2 Run strict OpenSpec, package/governance, diff, and delivery workflow checks with a fresh `origin/dev` base.
- [ ] 4.3 Record verification evidence, create small signed-off commits, push one branch, and open one PR targeting `dev` with `Closes #109`.
