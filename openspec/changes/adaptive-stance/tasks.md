## 1. Tests (RED first)

- [x] 1.1 RED: resolve_stance thresholds — every tier reached and left by
      its signals, recovered clarity steps down, out-of-range signals and
      unknown tiers/overrides rejected
- [x] 1.2 RED: S1 default-trust (ordinary proposal → no forced
      proportionality; magnitude signal → assessment), S2 novice posture +
      gather duty on axis overflow, S3 explicit challenges + axis freeze
- [x] 1.3 RED: computed signals drive plan()'s tier (registry vagueness,
      discipline rate, correction frequency); override wins; one-question
      hard gate in S2/S3 with S1 flag-not-block unchanged; score summary in
      blocked/handoff/waive

## 2. Implementation

- [x] 2.1 alignment_graph.py stance region: constants + `resolve_stance`
      (named thresholds, validated override)
- [x] 2.2 alignment_graph.py plan(): `stance` param, per-turn computed
      signals (fail-open #524/#525 consumption), `stance`/`stance_signals`
      emission, gather branch
- [x] 2.3 alignment_graph.py emission: `_gap_required_traces`
      signal-triggering, `_magnitude_signal`, S2 novice posture, gather
      terms, S3 challenge traces
- [x] 2.4 alignment_graph.py record(): S3 axis freeze + S2/S3 question
      hard gate (fail-closed before mutation)
- [x] 2.5 `_blocked_disposition`/handoff/waive `score_summary` transparency

## 3. Prose and packages

- [x] 3.1 SKILL prose: stance-awareness paragraph (tier names, per-tier
      changes, presume-competence anchor) in both host templates, within
      the forced-load word budget
- [x] 3.2 Regenerate packages (generated-only commit)
- [x] 3.3 Gates: full suite, ruff, validate, governance, parity,
      detect-changes reconcile → PR feat/issue-526-adaptive-stance → dev
      (do not merge)
