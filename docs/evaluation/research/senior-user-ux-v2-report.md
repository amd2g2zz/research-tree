# senior-user-ux-v2 — combined report

Dual-track evaluation executed 2026-09-01 per #451/#468. Track A: three
independent fresh-context role sessions re-ran the full 8/20 user journey.
Track B: one governed runtime run carried the real v2 oracle set through the
goal loop around the live-host injection matrix, plus two mechanism
supplements. Method boundary: Track A roles are agent sessions simulating
native roles (the 8/20 baseline roles were likewise agent sessions); no
third-party host binary was invoked (receipts disclose
`host_process_invoked: false`).

## Scores (kept separate per the baseline rule)

| Role | 8/20 baseline | v2 | Delta |
| --- | --- | --- | --- |
| Research architect | 76/100 | 68/100 | -8 |
| Platform engineering integrator | 65/100 | 64/100 | -1 |
| Governance auditor | 6.8/10 | 7.2/10 | +0.4 |

The three scores stay separate; the 6.8-basis governance score is not
averaged into the 100-point roles. The deltas are not uniform and must be
read per dimension, not as a single trend.

## What genuinely improved (with evidence)

- **Install-status integrity (8/20 P0)**: all three host copy-installs are
  byte-verified (`diff -qr`), digest-verified, and status-consistent; the
  8/20 status-conflict defect did not reproduce (integrator install matrix).
- **Handoff authority binding (8/20 P0 headline)**: confirmation binds every
  authority-bearing field via digest + authority fingerprint; stale-digest
  confirmation fails `confirmation_digest_mismatch`; post-confirmation
  authority broadening is impossible through the governed path (auditor
  probes `gov-audit-001/002`).
- **Fail-closed semantics**: 12/12 should-fail operations failed closed with
  canonical reasons (`run already exists`, `alignment graph changed after
  the displayed handoff draft`, strict verification schema,
  `illegal_transition`, ...).
- **Completion consistency**: `status`, `verify`, and `why-not-complete`
  agree exactly (12 = 3 static + 9 canonical obligations); the 8/20
  33-vs-30 contradiction class did not recur anywhere in v2.
- **Noise**: materially quieter than the 8/20 narrative (SQLite + per-event
  JSON instead of growing JSONL reread; architect ~3 duplicate reads and 0
  confirmed-material rereads; auditor 3 self-recorded duplicates, 0
  product-caused rereads). An exact percentage vs 8/20 is not computable —
  the 8/20 run never produced a numeric repeated-output count (baseline
  record protocol component 1 stays directional; components 2 and 3 pass).
- **Goal loop under load (Track B)**: the 13 real oracles survived a full
  governed run — 18/18 injection cells passed, per-oracle goal_satisfaction
  registered honestly (5 satisfied / 8 waived with reasons), independent
  delivery review with distinct identities, completion gate `completed`.
- **Contradiction detection**: contested pairs block decision authority,
  scope-separated pairs keep it, packets survive ledger round-trip
  (supplements receipt, 5/5 checks).
- **Contamination gate**: unsealed active outputs are rejected for reads and
  excluded from discovery; dispositions fresh/cached/replayed recorded; a
  declared duplicate-read budget exhausts into a resumable checkpoint that
  blocks further reads and confers no completion authority (supplements
  receipt, 8/8 checks).

## What regressed or remains broken (HIGH first)

1. **Operator lifecycle break (architect F1, integrator)**: a `prepared` run
   cannot reach `initialized` through any documented surface, so the
   strategy propose/display/confirm chain and all deliverables are
   unreachable from the operator journey; the alignment flow requires five
   internal Python APIs (Track B exercises them in-process — the mechanism
   works; the operator facade does not exist).
2. **Packaged `record` crash (architect F2, independently confirmed by the
   auditor)**: `python -m research_tree.alignment_graph record` fails with
   `ImportError: attempted relative import with no known parent package`
   (`speech_acts` is not packaged).
3. **Independence is label-deep (auditor)**: the display gate rejects
   self-labeled review, but independence is a string inequality between two
   self-declared fields; the 8/20 same-session rename attack passes by
   construction.
4. **Out-of-band ledger write (auditor)**: `revise_strategy` wrote a broad
   displayed projection plus a self-authored verification into the durable
   ledger after confirmation, with no invalidation marker.
5. **Operating model unexposed (integrator)**: the Human Research Report
   operating model (roles/SLA/concurrency/blockers/fallback) exists only
   inside `delivery.py` with zero CLI exposure (gate 8).
6. **Residuals**: internal obligation codes leak unexplained; `resume`
   reports success on a never-confirmed run; three static readiness
   failures persist permanently on a fully confirmed run; finding-pack
   schemas carry no executed/prototype/replayed/missing labels.

## Score attribution

The architect's -8 is concentrated in the operator-lifecycle dimension
(findings 1-2): the batch-3 goal-loop mechanisms are real (Track B proves
the chain in-process) but v2's tighter, surface-first sessions hit the
missing operator facade that the 8/20 sessions bypassed with 14M+ token
internal API archaeology. Part of the drop is stricter measurement, not
mechanism regression; the facade gap itself is real and unmet. The
auditor's +0.4 reflects the fixed authority-binding and clean fail-closed
record, offset by the label-deep independence finding.

## Verdict

Conditional adoption continues to hold, now with a sharper boundary: the
governed core (authority binding, fail-closed semantics, completion
consistency, contradiction detection, contamination gate, bounded-context
mechanisms) is materially stronger than 8/20; the operator facade (init
chain reachability, packaged CLI correctness, alignment/operating-model
exposure, independence robustness) is the single dominant gap and is the
next batch's scope (see the acceptance record for the per-gate table).
