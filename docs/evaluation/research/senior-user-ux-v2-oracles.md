# senior-user-ux-v2 — projection success oracles

The mechanical half of the #292 closure path (#451 prep checklist): the #292
acceptance gates and follow-up metrics are expressed as projection success
oracles with named evidence standards, so the v2 run's completion gate judges
closure oracle by oracle instead of by narrative summary.

- Source of truth: `evaluation/harness/v2_oracles.py`
- Mechanical check: `tests/test_v2_oracles.py` — a real `StrategyProjection`
  carrying `build_success_oracles()` / `build_decision_targets()` passes
  `validate_falsifiability`; gates 1-10 and every follow-up metric are
  coverage-asserted.
- Baseline: `senior-user-ux-20260820` (#292) — role scores 76/100,
  65/100, 6.8/10 are kept separate (no normalization without a declared rule).

## Gate → oracle mapping

| #292 gate | Oracle | Evidence standards |
| --- | --- | --- |
| 1 Handoff integrity | `oracle-handoff-integrity` | `es-handoff-fingerprint-match` |
| 2 One completion projection | `oracle-completion-consistency` | `es-completion-snapshot-digest` |
| 3 Actual independent review | `oracle-independent-review` | `es-verifier-identity-distinct` |
| 4 Operator-grade lifecycle | `oracle-operator-lifecycle` | `es-host-conformance-receipt` |
| 5 Preserved decision decomposition | `oracle-slot-decomposition` | `es-slot-closure-record` |
| 6 Bounded context discipline | `oracle-context-discipline` | `es-budget-receipt` |
| 7 Live-host evidence matrix | `oracle-live-host-matrix`, `oracle-recovery-semantics` | `es-host-matrix-receipt`, `es-recovery-reason-record` |
| 8 Adoption evidence | `oracle-operating-model` | `es-operating-model-payload` |
| 9 Freshness gate | `oracle-freshness-gate` | `es-freshness-decision-record` |
| 10 Independent rerun | `oracle-alignment-regression`, `oracle-evidence-honesty`, `oracle-completion-consistency`, `oracle-noise-reduction`, `oracle-recovery-semantics` | `es-role-transcript`, `es-boundary-disclosure`, `es-noise-measurement` |

## Decision targets

| Target | Question | Oracles owned |
| --- | --- | --- |
| `decision-track-a-ux-verdict` | Does the 8/20 conditional-use UX verdict hold with no regression and materially lower noise? | alignment-regression, evidence-honesty, completion-consistency, noise-reduction, operator-lifecycle, slot-decomposition |
| `decision-track-b-runtime-verdict` | Does the governed runtime survive live failure injection with the goal loop closed? | handoff-integrity, independent-review, live-host-matrix, recovery-semantics, context-discipline, slot-decomposition, completion-consistency |
| `decision-adoption-upgrade` | May the #292 conditional-adoption verdict be upgraded? | all thirteen oracles |

## Evidence standards and where the run must produce tokens

A finding pack satisfies a standard when its corroborated claims carry
matching tokens (grounding identities, provenance clusters, or grounding
artifact ids). The `token_basis` recorded per standard in the module names the
concrete artifact surface: authority fingerprints and compile-block records
(gate 1), completion snapshot digests (gate 2), alignment-verification /
delivery-review artifact ids (gate 3), host-conformance receipts (gate 4),
slot closure assessments (gate 5), budget/freshness receipts (gate 6),
baseline-comparison measurement records (gate 10 noise), the 18-cell
host-matrix receipt (gate 7), the `operating_model` delivery payload (gate 8),
freshness admission records (gate 9), per-role archived transcripts (Track A),
pack boundary disclosures, and canonical failure-reason records.

## Follow-up metric coverage

All thirteen follow-up metrics from #292 map to at least one oracle
(`METRIC_COVERAGE` in the module). The noise criterion is the strictest:
user-visible repeated output must fall at least 70% below the 8/20 baseline at
equal task coverage, and already-confirmed material must not be reread within
a bounded run unless its source digest or decision scope changed.

## How the v2 run consumes this module

Track B builds its strategy projection with
`success_oracles=build_success_oracles()` and
`decision_targets=build_decision_targets()` at run start, decomposes decision
slots by host x scenario serving those targets, and the completion gate then
requires per-oracle evidence in finding packs before any pass. Track A uses
the same oracle set as its scoring rubric so both tracks close the same
thirteen oracles with different evidence classes (receipts vs. role
transcripts).
