# senior-user-ux-v2 — baseline record (senior-user-ux-20260820)

The registered comparison point for the v2 dual-track evaluation (#451 prep
checklist, final item). The 8/20 baseline run itself is the baseline; this
record archives its measured numbers with declared counting bases, discloses
what was never counted, and declares the mechanical protocol the v2 run must
use so the #292 regression and noise-reduction judgments are checkable.

**Provenance and reachability disclosure.** The baseline evidence (per-role
reports, transcripts, runtime logs, summary.json) is retained with the
evaluation record referenced by #292 but is **not archived in this
repository**. Every number below is quoted from the #292 issue record; none
is re-derivable from in-repo artifacts. The v2 run admission step must
cross-check the baseline run name and role scores against this record, and
any future relocation of the baseline artifacts should update the pointer
here.

## Hard numbers (with counting basis)

| Quantity | Value | Basis |
| --- | --- | --- |
| Research architect score | 76/100 (conditional use for high-risk research pilots) | #292 role evaluation; scoring protocol per 8/20 run; formal score excludes an incomplete nested Docker/Hermes preflight |
| Platform engineering integrator score | 65/100 (isolated pilot viable; org-wide rollout not approved) | #292 role evaluation, same protocol |
| Governance auditor score | 6.8/10 (conditional approval; unsuitable for unsupervised final authorization) | #292 role evaluation, same protocol; scale differs from the 100-point roles |
| Research-architect run context cost | 14,071,408 input tokens in about 38 minutes | Host session token accounting at evaluation time, quoted in #292; accounting tool/version not recorded, not re-derivable in-repo |
| Governance run context cost | 17,223,731 input tokens | Same basis as above |

**Score-separation rule (#292):** the three role scores stay visible and
separate; the 6.8/10 governance score is never averaged into the 100-point
scores without a declared normalization rule. This rule is carried
mechanically by `METRIC_COVERAGE` in `evaluation/harness/v2_oracles.py`
("role scores kept separate without undeclared normalization").

## Qualitative baseline (observations, not counts)

Recorded in #292 as user-visible defects of the 8/20 run; these motivate the
noise oracles but were never counted:

- Repeated reconnaissance, long status output, tool errors, and retries caused
  advanced users to lose patience mid-run.
- Growing JSONL output was reread along with broad virtual-environment and
  cache scans (active-output/source-discovery contamination).
- A completion count conflict (executed `33 passed` vs `30 passed` in
  projections) and install-status conflicts after verified copy-installs.

## Never-counted quantities (declared)

The following 8/20 quantities have **no numeric baseline**; declaring this is
what keeps the v2 comparison honest:

- User-visible repeated-output count (the "≥70% reduction" anchor).
- Duplicate-read ratio, fresh/cached/replayed input split, tool/process output
  volume (the bounded-context metric set).

## v2 comparison protocol (declared, mechanical)

Because the pure "70% vs a counted 8/20 output volume" comparison is not
mechanically groundable, the v2 noise judgment (`oracle-noise-reduction`,
standards `es-noise-measurement` + `es-budget-receipt`) uses three declared
components:

1. **Token-volume proxy**: each v2 Track A role run archives its input token
   count at declared task coverage; the target is at least 70% below the
   #292-quoted per-role numbers. Directional: accounting bases differ across
   hosts and model versions, so the receipt must state its accounting basis.
2. **Absolute duplicate-read budget**: v2 budget receipts report the
   duplicate-read ratio with fresh/cached/replayed split; the run must meet
   the threshold it declares at admission (no baseline needed).
3. **Zero-reread clause**: no already-confirmed material is reread within a
   bounded run unless its source digest or decision scope changed — absolute
   and in-run verifiable.

Components 2 and 3 are the hard gate; component 1 is the baseline-anchored
directional check. The Track A "no regression" judgment
(`oracle-alignment-regression`, `oracle-evidence-honesty`) compares v2 role
narratives against the qualitative baseline above plus the archived role
scores, with scores kept separate per the rule.
