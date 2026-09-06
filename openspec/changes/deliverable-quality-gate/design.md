# Design: deliverable-quality-gate

## Approach

Follow the #462 independent-review pattern: the judgment is a host-produced
artifact; the engine validates its schema, its independence, and its binding,
then gates mechanically. No quality scoring lives in engine code — the engine
only verifies that a fresh-context review of the *current* draft deliverables
exists, passed, and is bound to the exact manifest digests.

### 1. `deliverable-quality-review` artifact (independent_review.py)

Payload schema 1, strict fields:

- identity pair `verifier_identity` + `session_context` (inherited #462
  contract; fail-closed without them — reuse `verify_identity_independent`).
- `manifest_digests`: `{technical_research_package: sha256,
  human_research_report: sha256}` — binds the review to exact draft bytes.
- `per_oracle`: non-empty `{oracle_id: {verdict: satisfied|unmet, basis}}`.
- `named_gaps`: sequence of `{description, target_slot_id, oracle,
  revive_node_id?}`. Required non-empty iff any per-oracle verdict is
  `unmet`; forbidden when all verdicts are `satisfied` (a pass is never
  quietly accompanied by unadjudicated gaps).

### 2. Gate on `finalize_research_delivery` (recursive_search.py)

After manifests are observed, the tree flips to `delivery_pending` only when
`deliverable_quality_gate.status == "passed"` and its recorded digests equal
the current manifest digests. Otherwise the tree becomes `blocked` with a
stop reason that names the pending gate (and, when stale, the digest
mismatch). Existing stop-reason wording keeps the `coordinator` anchor so the
authority test (`test_report_shape_is_observation_only`) survives unchanged.

### 3. `register_deliverable_quality_review` (recursive_search.py)

Pure state transition. Validates the payload, then:

- Rejects when either manifest lacks a registered `sha256`.
- Rejects stale reviews: recorded digests must equal current manifest digests.
- Rejects unknown `target_slot_id` / `revive_node_id` references.
- **Pass** → `deliverable_quality_gate = {status: passed, review_id,
  manifest_digests}`, status `delivery_pending`, coordinator stop reason.
- **Fail** → ReAct recovery: each named gap becomes mandatory frontier work
  on its target slot (a new remediation node, or — when the gap names one —
  the revival of a discarded node from the registry), the target slot reopens
  (`researching`, validation re-required), the gate records `failed` with
  `remediation_node_ids`, and the tree returns to `searching` with a stop
  reason naming the gap count. Remediation node ids follow the existing
  digest-based `node:<slot>:<hash16>` convention.

### 4. `discarded_evidence` registry (recursive_search.py)

`prune_research_state` appends one entry per node it defers or marks
duplicate: `{node_id, terminal_reason, decision_oracle, evidence_needed,
decision_slot_id, depth, selection_value}`. Append-only, deduped by
`node_id`. The registry is the revival source for remediation, so paid-for
depth stays queryable instead of dying in `terminal_reason` metadata.

### 5. Coverage-gated saturation (`_slot_evidence_saturated`)

For `landscape_required` slots with **no recorded batch comparison**
(`captures == 0`), saturation is refused: novelty 0 alone is process
exhaustion, not coverage. Slots with a recorded comparison keep the M6 gate
(capture-but-never-complete stays a gap); non-landscape slots are unchanged.

### State schema

`tree_state.py` gains two optional keys (the #492 pattern: legacy payloads
without them stay valid):

- `deliverable_quality_gate`: `{status: passed|failed, review_id,
  manifest_digests, remediation_node_ids}` (validated shape).
- `discarded_evidence`: sequence of registry entries.

`TREE_STATUSES` is unchanged; recovery reuses `searching`.

## impact_scope

- `finalize_research_delivery` (LOW, 1 upstream)
- `_slot_evidence_saturated` (7 upstream)
- `prune_research_state` (8 upstream)
- `initialize_research_state` (new default fields)
- new: `register_deliverable_quality_review`,
  `validate_deliverable_quality_review_payload`
- `validate_tree_state_payload` / `_OPTIONAL_TREE_STATE_KEYS` (tree_state.py)
- `research_tree.__init__` exports

## rejected_designs

- **Pass-with-notes evaluator**: a quality verdict that does not reopen
  named, actionable gaps is exactly the "weak deliverable sails through"
  failure this issue bans.
- **Engine-side quality scoring** (keyword checks, length heuristics on
  report text): violates the #501 two-layer contract — content quality is
  the reviewer's judgment; the engine verifies trace presence + binding.
- **Making LoopX/coordinator the quality authority**: the gate must be
  engine-verifiable and ledger-recorded like every other gate.
- **New tree status** (e.g. `quality_review_pending`): consumers branch on
  `TREE_STATUSES`; `blocked` + a named stop reason carries the same
  information without expanding the state machine.
- **Reviving discarded nodes by deleting registry entries**: the registry is
  append-only evidence; revival marks the node live, history stays.
