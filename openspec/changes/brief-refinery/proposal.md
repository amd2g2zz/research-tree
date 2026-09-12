# Proposal: brief-refinery

## Why

issue #524 (confirmed): user input and topics have no management, no signal
governance, no gate. User utterances enter the alignment graph as homogeneous
nodes — "must work offline" (hard constraint), "prefer lightweight"
(preference), "I heard X doesn't work" (environment claim) are
indistinguishable downstream, so verification strategy and gate semantics
cannot differ by type. The user ruled: topics/constraints are
**algorithmically extracted and aggregated (refined brief processing)** —
never user-declared structure; the only user action allowed is confirming a
mirror of their own words.

## What Changes

1. `src/research_tree/brief_refinery.py` (new): a typed topic/constraint
   registry. Extraction (`BriefRefinery.extract`) consumes model-produced
   candidate atoms (schema-validated by the engine — no keyword enums, per
   the #501 two-layer contract), clusters them, and applies conservative
   type defaults: every object starts `preference` or `environment-claim`;
   a candidate requesting `hard-constraint` is downgraded to `preference`.
   `hard-constraint` is reachable only through `confirm_hard_constraint`
   with a recorded confirmation reference.
2. Clustering reuse: claims.py gains one generic union-find surface
   (`cluster_identity_groups`); the existing `cluster_provenance_components`
   becomes a thin delegate (behavior preserved — pinned by existing claim
   tests). The refinery clusters its objects through the same surface — no
   second clustering implementation.
3. Lifecycle state machine: `open → clarified / parked / dropped / merged`
   (`parked` may reactivate to `open`); terminal states (`clarified`,
   `dropped`, `merged`) admit no outgoing transitions. Illegal transitions
   raise `IllegalLifecycleTransition` naming the rejected transition.
4. Persistence: `BriefRefineryStore` writes engine-owned state JSON with a
   SHA-256 digest under the run's `alignment/` directory
   (`brief-registry.json`), following the alignment_turn_record store
   pattern (strict whitelist schema, fail-closed read, digest verification
   on load).
5. Signal queries: `vagueness()` (share of live objects still open/parked)
   and `conflicts()` (conflict-pair count) feed the adaptive-stance
   controller. Conflict detection is engine-deterministic: same normalized
   topic with opposite polarity.
6. Closure-blocker query (additive seam only): `closure_blockers(`
   `observations)` returns named blockers for **confirmed** hard-constraint
   violations — the query the recursive_search blocker machinery can
   consume later. recursive_search itself is NOT wired in this issue;
   unconfirmed objects never block.
7. Turn-record delta seam (additive): `registry_delta(changes)` in
   alignment_turn_record.py converts a registry change set into the delta
   payload (`summary` + `nodes`) that `AlignmentTurnRecordStore.append`
   consumes — a user input's delta can now be precisely its registry
   changes (#497 no-delta check becomes accurate).

## Impact

- src/research_tree/brief_refinery.py: new module (engine-side registry).
- src/research_tree/claims.py: additive `cluster_identity_groups`;
  `cluster_provenance_components` delegates to it (behavior-preserving,
  impact: LOW — 3 direct callers).
- src/research_tree/alignment_turn_record.py: additive `registry_delta`
  helper only; no existing behavior changes.
- src/research_tree/__init__.py: additive exports.
- tests/test_brief_refinery.py: 10 scenario-named tests (RED first).
- brief_refinery.py is NOT a canonical skill input; skill parity must stay
  green with no regeneration.
