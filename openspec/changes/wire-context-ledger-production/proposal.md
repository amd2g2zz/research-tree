# Proposal: context-ledger production wiring + admission cross-check

## Why

The v2 acceptance record left two gate residuals (#472): the context-ledger
mechanism was fully proven (supplements receipt 8/8: sealing, discovery
exclusion, fresh/cached/replayed, declared-budget exhaustion producing a
resumable unknown checkpoint, no completion authority) but was not wired into
the production governed run path — the Track B receipt disclosed
`declared_budget: null`; the ledger receipt never reached the completion gate
as finding-pack evidence (the #466 producer obligation); and gate 9 had no
admission cross-check — the baseline doc's "cross-check the run name and role
scores" sentence was a recorded requirement, not an existing mechanism.

## What Changes

- NEW `evaluation/harness/v2_baseline_admission.py`: machine-readable
  baseline admission. `evaluation/baselines/senior-user-ux-v2-baseline.json`
  (registered-baseline, immutable by `content_digest` over its `baseline`
  payload) is the source of record for the baseline run name and the three
  role scores; `docs/evaluation/research/senior-user-ux-v2-baseline.md` is
  its human rendering and now names the registry. The run's declared
  baseline is cross-checked at run start: run-name or role-score mismatch,
  missing/unreadable/invalid registry, or digest mismatch fails closed with
  a canonical reason (`baseline-run-name-mismatch`,
  `baseline-role-score-mismatch:<role>`, `baseline-registry-missing`,
  `baseline-registry-unreadable`, `baseline-registry-invalid`,
  `baseline-registry-digest-mismatch`); a match returns the admitted
  cross-check record. NEW `evaluation/cases/senior-user-ux-v2.json` anchors
  the registry's `case_id` reference (registered-baseline entries must not
  dangle).
- Governed Track B runs (`run_v2_evaluation.run_governed_evaluation`)
  create a `ContextReadLedger` at
  `<workspace>/.research-tree/runs/run-v2-trackb/context/read-ledger.json`
  whose budget is declared at admission: the declared budget (and baseline
  run name + accounting basis) ride the confirmed strategy projection's
  autonomy envelope — requester-visible — and the persisted
  `context-admission-record` artifact. Cell receipts (the run's own active
  output) are sealed and read back through the ledger; the ledger receipt is
  grounded into `pack-context-evidence` under the `es-budget-receipt` token
  (closing the #466 producer obligation). An exhausted declared budget stops
  the run on the ledger's resumable unknown checkpoint: context-discipline
  registers `unmet`, the completion gate blocks, and the run never passes.
- `oracle-context-discipline` moves from the waived set to the
  runtime-satisfied set (its evidence is now genuinely produced); the
  receipt's `disclosures.declared_budget` carries the real declared value
  instead of `null`; the admission block and a `context` receipt section are
  added to the Track B receipt; `main` writes a `blocked` receipt and exits
  1 on admission failure.
- The contract stays in its current home (`scripts/context_ledger_contract.py`,
  packaged verbatim); the harness imports it the same way its sibling
  `v2_contradiction_contamination.py` does. No coordinator symbol changes.

## Impact

- Defaults unchanged for the 6x3 full matrix; subset runs (tests) stay green.
- `docs/evaluation/research/senior-user-ux-v2-baseline.md` prose updated:
  gate-9 requirement -> existing mechanism.
