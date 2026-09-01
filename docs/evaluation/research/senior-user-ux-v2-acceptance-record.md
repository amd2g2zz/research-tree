# senior-user-ux-v2 — acceptance record (#292 ten-gate reconciliation)

Executed 2026-09-01 (#468). Verdicts re-derived from raw artifacts (two
Track B receipts, three role summaries, three role reports, transcript
notes) and reconciled with an independent blind verifier. Bottom line:
**1 gate satisfied, 6 partial, 3 unmet — #292 stays open**; every miss is
attributed below and becomes the next batch's scope.

Evidence pointers: `TB` = `.research-tree/evaluation-runs/senior-user-ux-v2/track-b/receipt.json`;
`SUP` = `.../track-b/supplements-receipt.json`;
`A/I/G` = `docs/evaluation/research/senior-user-ux-v2-report-{research-architect,platform-integrator,governance-auditor}.md`
(+ their `track-a/<role>/summary.json`).

## Per-gate verdicts

| Gate | Verdict | Evidence and attribution |
| --- | --- | --- |
| 1 Handoff integrity | **satisfied** | Auditor probes: digest+fingerprint binding, stale-digest confirm rejected (`confirmation_digest_mismatch`), post-confirm broadening impossible through the governed path. TB `oracle-handoff-integrity` satisfied. Residual (next scope): `revise_strategy` out-of-band durable write post-confirmation lacks an invalidation marker (G). |
| 2 One completion projection | **partial** | G: `status`/`verify`/`why-not-complete` agree exactly (12 = 3 static + 9 canonical); the 33-vs-30 class did not recur in any v2 surface; TB `oracle-completion-consistency` satisfied. Downgraded per the independent verifier (adopted): three static readiness failures persist permanently on a fully confirmed run — that is itself a small canonical-vs-visible contradiction, so "satisfied" overclaims. |
| 3 Actual independent review | **partial** | TB exercises the full #462 double gate (display + delivery) with three distinct identities; self-labeled review is rejected (`independent_verification_required`). BUT independence is a string inequality between self-declared fields — the same-session rename attack passes by construction (G demonstrated), and `revise_strategy` wrote a self-authored verification post-confirmation. Next scope: structural identity (process/session lineage), not label equality. |
| 4 Operator-grade lifecycle | **unmet** (verifier reads partial: install matrix 3/3 clean is real credit; the unreachable strategy flow keeps the lifecycle from operator-grade — both readings recorded) | A F1: `prepared` -> `initialized` unreachable via any documented surface (strategy gates + deliverables cut off). A F2: packaged `record` crashes (`speech_acts` unpackaged; independently confirmed by G). I: alignment flow needs five internal Python APIs; `confirm` fails with unexplained `alignment_not_confirmed`; internal obligation codes leak; `resume` reports success on a never-confirmed run. Install matrix itself is clean x3 hosts (8/20 P0 fixed). Next scope: an operator facade over the existing in-process chain. Root cause isolated by the alignment-chain supplement: `coordinator.initialize` requires the compiled handoff in the blueprint target's parent_refs, but `CanonicalBlueprintTargetCompiler.compile` writes parent_refs as (brief, model) only and no CLI verb performs that binding — the prepared-to-initialized gap is a missing bridge, not a broken compile (the full in-process chain passes, see the alignment-chain receipt). |
| 5 Preserved decision decomposition | **unmet** | TB used the fixture-minimal slot shape (disclosed as the `slot_decomposition` waiver); no role run reached decision-slot closure through a product surface (gate 4 blocks it). Next scope: decompose inside the operator facade once gate 4 lands. |
| 6 Bounded context discipline | **partial** | SUP proves the mechanisms end-to-end: unsealed active-output rejection, sealing, fresh/cached/replayed dispositions, discovery exclusion, declared budget exhausted -> resumable checkpoint that blocks reads and confers no completion authority, resume re-opens the next wave. GAP: the ledger is not wired into the production run path (`declared_budget: null` in TB); roles observed quiet behavior informally (A ~3 duplicates / 0 confirmed-rereads; G 3 self-recorded / 0 product rereads). Next scope: wire the context ledger into every governed run + declare budgets at admission. |
| 7 Live-host evidence matrix | **partial** | TB: 18/18 canonical receipts reachable, per-cell provenance and `host_process_invoked: false` disclosed (mechanism level, same as gate7 #461). Still no third-party host binary in the loop. Next scope: live host receipts in a real host environment. |
| 8 Adoption evidence | **unmet** | The operating model exists only inside `delivery.py` with zero CLI exposure (I); Human Research Report unreachable through an operator surface. Gate 4's facade is the blocker here too. |
| 9 Freshness gate | **unmet** | As disclosed in the baseline record, the admission cross-check is a recorded requirement, not an existing mechanism; the v2 run orchestration lane did not execute it. Next scope: implement the cross-check (baseline run name + role scores vs the baseline record) in the run-orchestration lane. |
| 10 Independent rerun | **partial** | The fresh rerun happened (this evaluation, three fresh roles + governed run). Alignment/evidence honesty mechanics show no regression (G +0.4, fail-closed 12/12, boundary honesty holds); noise is materially lower by the declared protocol (component 2/3 hard gates pass; component 1 directional — no contradictory completion display anywhere). The architect's -8 is operator-facade concentration, not alignment/honesty regression — but until gate 4 lands the rerun cannot be rated "materially better end to end". |

## Score summary (separate, per the baseline rule)

76 -> 68 (architect), 65 -> 64 (integrator), 6.8 -> 7.2 (auditor). Deltas
attribute per dimension in the combined report; no averaging.

## Independent verification

A fresh-context verifier re-derived the per-gate table from raw artifacts
only (receipts, summaries, transcript notes), reproduced the record crash
and the label-deep independence attack itself, and reproduced the
post-confirm `revise_strategy` broadening (broad displayed projection
persists with no invalidation marker). Verdict: **SUPPORTED**. Adopted
amendments: gate 2 downgraded to partial (static readiness contradiction);
gate 7 recorded as partial with the explicit note that the Track B
satisfied verdict for `oracle-live-host-matrix` follows the disclosure-only
oracle statement while the #292 gate text demands actual host runs
(verifier MEDIUM); gate 4 carries both readings. Provenance note: role
sessions started at 6d3996a and the branch advanced to 5c281cc mid-run;
the diff touches only evaluation harness and tests, so the evaluated
product surface is identical.

## Closure decision

#292 remains **open**: gate 1 satisfied; gates 2/3/4/6/7/10 partial; gates 5/8/9 unmet. Next-batch
scope (attributed): operator facade (gate 4 -> unblocks 5/8), independence
hardening (gate 3 residual), context-ledger wiring (gate 6 residual),
admission cross-check (gate 9), live-host receipts in a real host
environment (gate 7 residual). #451 closes with this record: its checklist
is complete and the run executed.
