# Tasks: persist-alignment-turn-record

## 1. SDD

- [x] 1.1 Proposal, design (`impact_scope` + `rejected_designs`), capability
  spec delta from issue #497 scenarios.
- [x] 1.2 GitNexus index rebuild + upstream impact per modified symbol
  (`observe`, `_observe_prompt_signal`: both LOW).

## 2. Turn-record persistence store (RED first)

- [x] 2.1 RED: a 4+ turn simulated conversation appends one record per turn
  to the alignment workspace file — the file exists, grows by exactly one
  JSON line per turn, and every record round-trips mirror/gap/delta/
  user-move; `user_move` is validated against the `turn_contract` response
  classes; `contract_terms`/`traces` round-trip through the seam schema and
  `verify_traces` fails on a missing required trace.
- [x] 2.2 RED: the continuity gate reads before allowing the move —
  `check_continuity(next_turn)` returns the grounding (latest mirror/gap/
  delta) when the latest record is adjacent, and allows re-grounding when
  this exchange's record is already persisted.
- [x] 2.3 RED: fail-closed blocks with named reasons — missing file
  (`missing_turn_record`), malformed record (`invalid_turn_record`), skipped
  exchange (`stale_turn_record`); `append` refuses out-of-order turn indices.

## 3. Self-ask/self-answer guard (RED first)

- [x] 3.1 RED: a turn attempt with no persisted delta (empty/blank
  `delta.summary`) is rejected as a protocol violation; a delta naming
  touched graph nodes persists normally.

## 4. Hook refresh and validation (RED first)

- [x] 4.1 RED: `UserPromptSubmit` on an active alignment-phase run refreshes
  and validates the record file — verdict (`validated`/`missing`/`invalid`)
  is on the hook result and the sanitized record; a validation receipt is
  written next to the records.
- [x] 4.2 RED: `PostToolUse` performs the same refresh after the event is
  recorded; compaction simulation — after the hook refresh continuity holds
  (gate allows), while a deleted or corrupted record file fails validation
  and the gate blocks the next turn.
- [x] 4.3 RED: without an active run (or outside alignment with no record
  file) the hook adds no turn-record verdict and stays fail-open; existing
  #503 re-entry behavior is unchanged.

## 5. Implementation (GREEN)

- [x] 5.1 `src/research_tree/alignment_turn_record.py`: record schema,
  JSONL store, continuity gate, delta guard, validation refresh; stdlib-only,
  reusing `turn_contract` (no schema duplication, no seam edits).
- [x] 5.2 `src/research_tree/lifecycle_hook.py`: defensive import,
  `UserPromptSubmit`/`PostToolUse` refresh wired fail-open; #503 re-entry
  logic untouched.
- [x] 5.3 GREEN: sections 2-4 pass; existing suites (including
  `test_lifecycle_hook_reentry.py`) stay green.

## 6. Prompt layer

- [x] 6.1 `skill-src/SKILL.template.md` +
  `skill-src/hermes-SKILL.template.md`: the alignment-turn-record clause
  gains the record-or-block enforcement wording (persistence clause only).
- [x] 6.2 Regenerate `packages/**` via `build_skill_packages.py` in a
  generated-only commit; parity gate green.

## 7. Gates and evidence

- [x] 7.1 Full local gates green: pytest (no new failures), ruff check +
  format check, `check_delivery_workflow.py validate`,
  `check_openspec_governance.py`, `build_skill_packages.py --check`.
- [x] 7.2 GitNexus `detect-changes` reconciled with this `impact_scope` via
  `check_impact_scope.py`; reports stored in `evidence/`.
