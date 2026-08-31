# Assess Goal Contribution

## Why

After a Finding Pack passes strict compile and evidence review, nothing asks the only
question that matters at run level: did this result advance the `decision_target` the
slot `serves`? Slots accumulate evidence that never closes their decision, and dispatched
work with defective guidance burns workers silently. Issue #428 makes contribution
judgment coordinator authority (maker-checker: the pack's maker never self-stamps goal
relevance) and closes the loop with a guidance-adjust retry.

## What Changes

- Add coordinator pure function `assess_goal_contribution(pack, slot, projection)` with
  the verdict enum `advances / partial / no_contribution / contradicts` over a
  short-circuit truth table (contradicts → advances-by-effect → advances-by-claim →
  partial → no_contribution). The verdict never reads worker confidence.
- On accepted (compile-passed) Finding Pack ingestion, the coordinator appends a
  `goal-contribution-assessment` artifact with exact lineage: finding pack + slot +
  confirmed projection digest, `parent_refs = (finding_pack, strategy_projection)`.
- `advances/partial` packs keep the prior consumption behavior; `no_contribution/`
  `contradicts` packs are excluded from the tree transition `consumed` set (ingest and
  restart recovery both honor the recorded verdicts).
- Blocking verdicts trigger the guidance-adjust retry through `record_same_round_replan`
  extended to slot granularity: payload keys `affected_slot_ids` and `guidance_defect`,
  plus a successor Work Item with adjusted guidance recording the defect.
- The second consecutive `no_contribution` on the same slot consults the scheduling
  policy with a `method_switch` deficit (ADR-006 wiring) and flags the successor item
  `redecomposition_flagged: true` — never a silent re-dispatch of identical guidance.
- `CanonicalWorkItemCompiler.compile` gains optional `guidance_defect`,
  `redecomposition_flagged`, and `policy_proposal_id/kind` lineage fields.

## Capabilities

### New Capability: goal-wiring

### Modified Capabilities

(none)

## Impact

- `src/research_tree/coordinator.py` — pure truth table, partition helper, assessment +
  retry wiring on `ResearchRunCoordinator`, replan payload extension.
- `src/research_tree/ledger.py` — compile hook assessing every compile-passed pack.
- `src/research_tree/recursive_search.py` — ingest/recover consult recorded verdicts
  before the tree transition consumed set.
- `src/research_tree/work_items.py` — optional retry lineage fields on the work item.
- `src/research_tree/feedback.py` — same-round replan payload whitelist extended to
  slot granularity (`affected_slot_ids`, `guidance_defect`).
- tests: new `tests/test_goal_contribution.py` contract tests.
