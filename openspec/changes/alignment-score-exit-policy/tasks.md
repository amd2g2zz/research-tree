# Tasks: alignment-score-exit-policy

## 1. SDD

- [ ] 1.1 Proposal, design (`impact_scope` + rejected designs), capability
  spec delta from issue #491 scenarios.
- [ ] 1.2 GitNexus index rebuild + upstream impact per symbol (`plan`,
  `confirm`, `record` LOW; `_materialize` CRITICAL and excluded from the
  change surface).

## 2. Blocked disposition on the turn cap (RED first)

- [ ] 2.1 RED: with an open high-impact requester-only gap, six user turns
  (each opening a new divergence axis, composing with #496) end in an
  `alignment_incomplete` decision — never `reconnaissance` — naming the gap in
  `blocked_nodes`, the spent ask budget in `exhausted_ask_nodes`, and the
  score below the threshold.
- [ ] 2.2 RED: with the ask budget spent on a high-impact requester-only gap
  and no dialogue move left, `plan()` escalates to `alignment_incomplete`
  naming the node instead of the stall/agent-verifiable reconnaissance; with
  the same shape at low impact the #496 stall reconnaissance is preserved.
- [ ] 2.3 RED: `record()` reports `next_action: "alignment_incomplete"` (not
  `reconnaissance`) when the dialogue is stalled on an exhausted high-impact
  gap.

## 3. Score gate and user decision paths (RED first)

- [ ] 3.1 RED: a satisfied score allows the normal handoff path
  (`await_human_confirmation` + `confirm`); an open divergence axis on a
  settled node lowers the score below the threshold, keeps `plan()` in
  dialogue (exploratory `ask_one` on the axis-bearing node), and makes
  `confirm()` raise the below-threshold error under user pressure.
- [ ] 3.2 RED: an explicit `waive(reason)` records the waive, re-opens the
  exit (`await_human_confirmation` then `confirm` succeeds); without the
  waive the exit stays blocked; a graph change after the waive expires it.
- [ ] 3.3 RED: a user response after a blocked disposition re-opens the
  dialogue for `ALIGNMENT_EXTENSION_TURNS` turns; past the window the blocked
  disposition returns; a further response re-arms it.

## 4. Implementation (GREEN)

- [ ] 4.1 Score constants + `_alignment_score`; exit gate in `plan()` and
  `confirm()`; additive `alignment_score`/`alignment_exit_threshold` keys.
- [ ] 4.2 `_blocked_disposition` + `_escalation_nodes`; turn-cap branch
  replaced; escalation branch added; `record()` `next_action` override.
- [ ] 4.3 `waive()` store/CLI surface + `_active_waive` digest binding;
  `_extension_deadline` event-log derivation.
- [ ] 4.4 Verify no existing test encodes the removed turn-cap escape; all
  existing alignment tests unchanged and green.

## 5. Gates and evidence

- [ ] 5.1 Full local gates green: pytest (no new failures), ruff check +
  format check, `check_delivery_workflow.py validate`,
  `check_openspec_governance.py`, `build_skill_packages.py --check`.
- [ ] 5.2 Regenerate `packages/**` in a generated-only commit.
- [ ] 5.3 GitNexus `detect-changes` reconciled with this `impact_scope` via
  `check_impact_scope.py`; reports stored in `evidence/`.
