# Proposal: deliverable-quality-gate

## Why

issue #495 (confirmed): research ends when the *process* runs out (novelty 0,
frontier empty, budget), never when the *deliverable* is good. Three engine
holes: (a) `finalize_research_delivery` flips a tree to `delivery_pending` as
soon as both report manifests merely exist (bytes + headings floor), (b) there
is no evaluator that judges draft deliverables against the confirmed
projection's success oracles before delivery, and (c) pruned/deferred work —
with its oracle and evidence need — lives only in node metadata
(`terminal_reason`), so paid-for depth is not queryable for recovery.
Symptom bundle: 马上开调研、马上结束调研，给个不太行的东西就收尾.

## What Changes

1. `deliverable-quality-review` artifact kind (independent_review.py): a
   fresh-context reviewer reads the draft deliverables plus the confirmed
   projection's success oracles and records per-oracle verdicts plus NAMED
   gaps. Independence is inherited from the #462 identity-pair contract
   (fail-closed without it); the review binds to the manifest sha256 digests
   so a review of stale deliverables cannot pass later ones.
2. `register_deliverable_quality_review` (recursive_search.py): validates and
   records the review. On failure it converts each named gap into remediation
   frontier work — a new node on the target slot, or the revival of a
   discarded node when the gap names one — and reopens the target slot
   (ReAct-style recovery, not pass-with-notes).
3. `finalize_research_delivery` gate: `delivery_pending` now requires a
   passing quality review bound to the *current* manifest digests; manifests
   alone yield a blocked state naming the pending gate.
4. `discarded_evidence` registry (recursive_search.py): every pruned node is
   recorded with terminal reason, oracle, evidence need, and slot so the
   remediation loop can revive it.
5. Coverage-gated saturation (`_slot_evidence_saturated`): a landscape slot
   with no recorded batch comparison never saturates on novelty alone —
   coverage must be measured, not skipped.

## Impact

- src/research_tree/independent_review.py: one additive artifact kind +
  validator, no changes to existing kinds.
- src/research_tree/recursive_search.py: gate on finalize, one new pure
  registration function, one state registry field, one saturation guard.
- Neither file is a canonical generation input; no package regeneration.
- No new tree status values: `delivery_pending` keeps its meaning, it is now
  gated; recovery uses the existing `searching` state.
