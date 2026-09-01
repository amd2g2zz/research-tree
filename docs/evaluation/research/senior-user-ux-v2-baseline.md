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
is re-derivable from in-repo artifacts. The pointer of record for the
baseline artifacts is the #292 evaluation record itself. Requirement on the
v2 run orchestration (the remaining #451 checklist work): the admission step
cross-checks the baseline run name and the three role scores against this
record and archives the cross-check in the admission receipt — until that
lane lands, this sentence is a recorded requirement, not an existing
mechanism.

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
scores without a declared normalization rule. This rule is tracked as a
follow-up metric mapped to `oracle-alignment-regression` (`METRIC_COVERAGE`
in `evaluation/harness/v2_oracles.py`, coverage-asserted by tests); the
coverage row records the rule, it does not enforce it — enforcement lives in
the oracle statement prose judged at the completion gate.

## Qualitative baseline (observations, not counts)

Recorded in #292 as user-visible defects of the 8/20 run; these motivate
the noise oracles but were never counted as repetition measurements (the two
counts below are issue-quoted incident figures, not repetition baselines):

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
components. The committed oracle set carries this protocol: the
`oracle-noise-reduction` statement and the `es-noise-measurement` token
basis were amended in the same change as this record (the pre-amendment
statement hardcoded a pure output-count comparison that no baseline count
can ever satisfy).

1. **Token-volume proxy**: each v2 Track A role run archives its input token
   count at declared task coverage; the target is at least 70% below the
   #292-quoted per-role numbers. Anchors exist for two roles only
   (research-architect, governance-auditor); the platform-integrator role has
   no #292-quoted number, so its first v2 count becomes its own reference
   until a baseline number is registered. Directional: accounting bases
   differ across hosts and model versions, so the receipt must state its
   accounting basis.
2. **Duplicate-read budget (declared, not self-enforcing)**: v2 budget
   receipts report the duplicate-read ratio with fresh/cached/replayed
   split, checked against the threshold declared at admission (no baseline
   needed). Loophole, acknowledged: the machinery accepts any declared value
   in [0, 1] — including one that can never fire — and "declared task
   coverage" is likewise run-attested. The declaration is therefore bound to
   human and independent review: the threshold and coverage statement are
   part of the confirmed strategy projection, and their reasonableness is
   judged by the independent verifier (`es-verifier-identity-distinct`) and
   the Track A/B reviewers, not by machinery alone.
3. **Zero-reread clause**: no already-confirmed material is reread within a
   bounded run unless its source digest or decision scope changed — absolute
   and in-run verifiable.

Components 2 and 3 are the hard gate relative to what the run declares and
registers; component 1 is the baseline-anchored directional check. Strength
disclosure: the completion gate checks per-oracle registrar attestation — a
`goal_satisfaction` registration with evidence refs resolving to run
artifacts, evidence standards entering via token identity, and a first-class
waiver path that counts with a prose reason. What makes the gate more than
self-declaration is the independent-review oracle: a distinct verifier
reviews the registrations and waiver reasons against the declared budgets.
Two producer obligations sit with the v2 run orchestration lane: wrap
read-ledger receipts (which live as run files) into registered finding-pack
evidence so the gate can see them, and state whether each Track A role
session is adapter-mediated or natively accounted — the 8/20 token numbers
came from external host accounting, and the v2 receipts must name their own
accounting basis. The Track A "no regression" judgments compare different
objects per oracle: `oracle-alignment-regression` compares v2 role
narratives against the 8/20 baseline role reports — artifacts archived with
the #292 evaluation record, not in this repository — while
`oracle-evidence-honesty` is an absolute in-run constraint on v2 projections
with no baseline comparison. Role scores stay separate per the rule.
