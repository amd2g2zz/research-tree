# senior-user-ux-v2 — independent verifier report (committed artifact)

Verifier: fresh-context subagent, identity `v2-independent-verifier`
(separate session from the orchestrator, the three Track A roles, and the
Track B harness author). Inputs: raw artifacts only — the two Track B
receipts, the three role `summary.json` files, transcript notes, the role
reports, `evaluation/harness/v2_oracles.py`, the baseline record, and GitHub
issues #292/#451. The orchestrator's synthesis was not available to it
(blind). Its output below is the reconciliation basis for the acceptance
record; the orchestrator adopted two of its readings (gate 2 downgrade,
gate 7 partial note) and recorded one difference (gate 4 weighting).

## Verifier verdict (verbatim conclusion)

SUPPORTED — the v2 artifacts support the per-oracle/gate judgments as
re-derived.

## Independent reproductions (run by the verifier itself, not transcribed)

1. Packaged record crash (architect F2): CONFIRMED — direct-script
   invocation of `packages/codex/research-tree/scripts/alignment_controller.py`
   crashes with `ImportError: attempted relative import with no known parent
   package` (alignment_controller.py:331, `from .speech_acts import ...`);
   `speech_acts.py` exists in no packaged `scripts/` directory.
2. Label-deep independence (auditor F1): CONFIRMED by probe — self-labeled
   verification accepted at write; display rejected
   `independent_verification_required`; same-process distinct-name
   verification passes display (rc 0).
   `src/research_tree/independent_review.py:57-67` is a string inequality
   of two self-declared fields.
3. Post-confirm out-of-band broadening (auditor F2): CONFIRMED — after
   confirm of a narrow envelope, `coordinator.revise_strategy`
   (coordinator.py:848, unconditional `status: "displayed"` at :868)
   appended a broad revision to the durable ledger; re-display is rejected
   (fail-closed) but the broad displayed record persists with no
   invalidation marker.

## Verifier's per-gate table (re-derived)

| Gate | Verifier verdict | Adopted by the acceptance record |
| --- | --- | --- |
| 1 | GATE-PASS | satisfied |
| 2 | PARTIAL (3 static readiness failures permanently contradict canonical state) | **partial — downgrade adopted** |
| 3 | PARTIAL (string-inequality independence) | partial |
| 4 | PARTIAL (install matrix 3/3 clean; strategy flow unreachable) | unmet, with the verifier's partial reading recorded in the row |
| 5 | GATE-FAIL | unmet |
| 6 | PARTIAL (mechanisms proven in-process; `declared_budget: null` for the actual run) | partial |
| 7 | PARTIAL (18/18 receipts but `host_process_invoked: false`; gate text demands actual host runs — verifier MEDIUM) | partial, with the MEDIUM noted |
| 8 | GATE-FAIL | unmet |
| 9 | GATE-FAIL (no admission record exists) | unmet |
| 10 | PARTIAL (rerun happened, scores separate, no contradictory display; token proxy unmeasurable; two scores dropped) | partial |

## Discrepancies raised and their disposition

1. MEDIUM — gate 7 satisfied-vs-gate-text (disclosure-only oracle vs
   "actual host runs"): adopted; gate 7 stays partial.
2. MEDIUM — `oracle-independent-review` Track B satisfaction covers only
   half its statement (no rejected self-issued artifact in the TB ledger;
   the demonstration lives in Track A): acknowledged; gate 3 stays partial.
3. LOW — `completion_gate.state` serialized as `"None"`: fixed in
   `run_v2_evaluation.py` (state now null when absent) and receipts
   regenerated.
4. LOW — provenance drift (roles started at 6d3996a, branch advanced to
   5c281cc mid-run): disclosed in the acceptance record; diff touches only
   harness/tests.
5. LOW — supplements receipt lacked the declared threshold: fixed
   (`declared_max_duplicate_read_ratio: 0.1` now in the receipt).
6. LOW — `interruption:hermes` launcher-binding limitation: disclosed and
   pass-criterion unaffected.
7. INFO — integrator rank-4 severity (resume on never-confirmed run):
   recorded as bookkeeping, not a completion claim.
8. INFO — all 8 waiver reasons verified accurate against artifacts.
