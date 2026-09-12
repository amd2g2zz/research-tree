# Design: adaptive-stance

## Approach

The stance is a finite engine-computed enum (S1/S2/S3) carried beside the
contract terms — never a behavior: the posture content stays prompt-layer
per #501. All four signals are already measured by the engine, so the
computed path needs no new input surface: clarity is the #491 alignment
score plan() already derives, vagueness and conflict come from the #524
brief-registry queries, conflict adds the #490 correction frequency counted
in the bounded user-move feed scan, and violation_rate is the #525
sliding-window rate over the persisted violation stream. Everything is
read-only consumption behind the module's existing fail-open import seam
(the packaged single-file controller has neither store beside it and
degrades to clean signals → S1).

### resolve_stance (thresholds)

```
tier = S1
if vagueness >= 0.5:        tier = S2     # the user does not know what they want
if conflict >= 2 or violation_rate >= 0.4: tier = S3   # error/conflict (0.4 = the #525 reload bar)
if clarity >= 85 and tier != S1: tier steps down one level  # recovered clarity
```

`override` (the explicit user-side input) beats the computed tier and is
validated like every other stance value; out-of-range signals raise
`AlignmentGraphError`. Critical moments (decision-critical steps) go through
the same declared-override path — the engine never infers from text. The
thresholds are module constants, test-pinned at both boundaries.

### Tier-shaped emission

`_gap_required_traces` stops making proportionality unconditional on
proposal shape: a magnitude signal (impact ≥ 4 — the high-impact bar — or a
node-attributes `proportionality_assessment.direction` of over/under from
the #498 fields) is required in S1/S2; ordinary proposals carry it only in
S3, where `counterargument` also surfaces as an explicit required trace
(queued per the #527 two-per-turn cap when a third name applies). S2 reuses
the #520 novice posture as emission policy; the disputed/reopen
`guess-statement` floor stays first at every tier.

The gather duty: with more than `MAX_ACTIVE_AXES = 2` open divergence axes,
plan() emits a `gather` decision (non-question, no ask consumed) grounded on
the first open axis's node, with `gather_options` carrying the open topics;
the emission requires `option-set` under the discrimination floor, ahead of
the carried deferral queue so the duty never defers. S1 keeps the #496
behavior (record axes, do not chase them).

### Invariants and gates

record() reads the outstanding plan's persisted stance (fail-open to the
#527 flag-not-block behavior when none was emitted): in S3 `new_axes` are
refused (convergence first); in S2/S3 a `max_questions` budget violation is
a hard gate (fail-closed before mutation) instead of a flag. Both gates sit
beside the trace verification, so a refused turn persists nothing.

### Score transparency

`_score_summary(score, remaining)` renders "understood ~N%; remaining: X"
into the blocked disposition (remaining = open gap ids), the handoff
decision (remaining = open axis descriptions), and the waive result
(remaining = blocked nodes) — the waive reads as a mutual "good enough"
acknowledgment. The exit threshold itself stays 100 in this change: a
calibrated-band exit re-keys the whole #491 exit policy and belongs to a
follow-up (the transparency mechanism here is its precondition).

## Alternatives considered

- A separate stance.py module: rejected — the packaged single-file
  controller is a byte-copy of alignment_graph.py with a fixed file map, so
  the logic must travel inside it.
- Stance inside ContractTerms: rejected — turn_contract is a frozen seam
  with strict field sets; the decision dict already carries additive
  dispositions (`question_budget`), and terms stay tier-agnostic.
