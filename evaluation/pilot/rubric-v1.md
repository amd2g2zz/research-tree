# Paired Pilot Rubric v1

Four stages scored independently, 3-5 dimensions each, 0-3 per dimension.
**No aggregate score.** Stage numbers are never summed, weighted, or averaged.
An arm is compared per stage, per dimension, per case — nothing else.

## Scoring anchors (per dimension)

| Score | Anchor |
|---|---|
| 0 | Absent or actively wrong (fabricated, contradicts own evidence) |
| 1 | Present but shallow (generic, unanchored, or one-sided) |
| 2 | Adequate (evidence-anchored, scope-respected, minor gaps) |
| 3 | Strong (precise, adversarially checked, actionable, honest about limits) |

## Stage 1 — Alignment

1. Intent capture: does the round's final understanding reflect the requester's
   actual decision problem (including corrections during the round)?
2. Scope negotiation: were hidden requirements surfaced and expansions labeled
   as agent proposals?
3. Authority boundaries: who decides what — explicitly respected?
4. Interruption handling: did a mid-run ask route through the correction
   protocol (observable lineage) rather than prose improvisation?

## Stage 2 — Evidence

1. Method diversity: did the arm try materially different methods/providers,
   or one method with cosmetic variation?
2. Provenance discipline: are claims traceable to pinned sources (digests,
   revisions), with independent provenance groups actually independent?
3. Contradiction handling: were conflicts surfaced, scoped, and resolved or
   explicitly left open?
4. Counterevidence: did the arm actively seek disconfirming evidence for its
   own early conclusions?

## Stage 3 — Synthesis

1. Claim admission honesty: do conclusions respect the evidence standard
   (corroborated vs single-source vs speculative), with admission outcomes
   visible?
2. Decision support: does the synthesis map to the decision slots it claims to
   close?
3. Uncertainty honesty: are residual unknowns and reversal conditions stated?

## Stage 4 — Delivery

1. Technical package actionability: could an engineer implement from it
   (paths, symbols, ordered work, validation)?
2. Human brief fidelity: plain-language, decision-oriented, no schema dumping.
3. Acceptance protocol: was the human acceptance decision collected and
   recorded (5-outcome), not assumed?
4. Stale marking: on post-delivery contradiction, were affected deliveries
   marked stale and re-entry offered?

## Blind-eval protocol

1. Outputs are anonymized to `arm-a` / `arm-b` before the evaluator sees them;
   the mapping is held by the operator and revealed only after all scores are
   committed.
2. Evaluators see, per case per arm: the full transcript, both deliveries,
   `research-tree status` / `verify` outputs, and the recorded process metrics.
3. Scores are committed per stage/dimension/case in one pass; no revisiting
   after unblinding.
4. If an arm failed to produce an output for a stage, that stage's dimensions
   score 0 with a `not-produced` note — never skipped.

## Process metrics (recorded per case per arm, not scored)

method-diversity count; provenance-group count; claim-admission outcomes
(corroborated / isolated / rejected); contradiction count; human turns; and
for A2 only: correction-event and stale-delivery counts.
