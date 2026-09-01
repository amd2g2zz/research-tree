# Proposal: independent-subagent-review

## Why

Issue #462 records the #292 gate 3 defect: alignment conclusions and the
delivery verdict are produced and reviewed inside the main agent's own
context — no independent subagent analysis, no independent subagent
verification. Original research content keeps accumulating in the main
context and the coordinator reviews its own work under different labels,
which #292 gate 3 explicitly excludes: "required review records distinct
execution identities, session/context lineage, evidence custody, oracle
custody, and authority; self-review cannot satisfy an independent gate."

## What Changes

- New artifact contracts in `src/research_tree/independent_review.py`,
  produced host-side and persisted through the existing typed
  completion-input channel (`CompletionInputRegistrar`, roles
  `alignment_verification` and `delivery_review`):
  - `alignment-verification` (schema 1): the subagent's independent
    restatement of outcome, scope, authority, and every success oracle,
    plus discrepancies with the draft, bound to the projection content by
    the #450 authority fingerprint and to the read projection revision
    through parent lineage.
  - `delivery-review` (schema 1): per-oracle independent verdicts
    (satisfied | partial | unmet with a basis), evidence custody
    references bound as parent lineage, an overall verdict, and the
    reviewer identity.
- Both artifacts record `verifier_identity` (the subagent's session or
  execution identity — the same identity carrier the lifecycle hook
  records host-side) and `session_context` (the session/context lineage
  the review is bound to, the dispatching main session). Independence is
  judged by inequality of the two identities; missing or blank identity
  is fail-closed, never independent.
- Display gate (#462): `research-tree strategy display` and every caller
  of the `alignment_projection_ready` transition require a current
  alignment verification whose fingerprint matches the projection, whose
  verifier identity is independent, and whose restatement covers every
  projection oracle; otherwise the display is rejected with
  `independent_verification_required`. A CLI display pre-flights the gate
  so a rejected display appends no artifact.
- Delivery gate (#462): a new `independent_delivery_review` diagnostic in
  the coordinator completion manifold requires exactly one current
  delivery review that is identity-independent, whose custody references
  match its parent lineage and still resolve to current, non-quarantined
  run artifacts, whose per-oracle verdicts cover every confirmed
  projection oracle, and whose overall verdict is not `unmet`; otherwise
  `delivery_accepted` is blocked with
  `independent_review_required`, `verifier_not_independent`,
  `evidence_custody_lineage`, `evidence_custody_stale`,
  `oracle_uncovered`, or `independent_review_unmet`.
- Conjunction, not replacement: the #441 falsifiability review and the
  #443 goal_satisfaction diagnostic keep their exact semantics and run
  beside the new gates; any single failing gate blocks.
- SKILL.template.md, hermes-SKILL.template.md, and the three host
  adapters gain one dispatch instruction each: display and delivery
  require dispatching a fresh-context subagent (read what, produce what),
  and self-issued reviews are rejected.

## Impact

- `src/research_tree/independent_review.py` (new),
  `completion_inputs.py` (two registrar writers),
  `run_ledger.py` (two completion-input roles), `coordinator.py`
  (display gate, transition guard, completion diagnostic),
  `cli.py` (display pre-flight), and the regenerated host packages.
- Existing callers of display and completion now need the review
  artifacts; tests updated at the shared helpers
  (`tests/strategy_support.py` and the coordinator fixtures).
- No stored-history migration: new writes only (alpha3 zero-compat
  ruling). Runs from earlier revisions fail closed on the new gates
  until an independent review artifact is produced.
