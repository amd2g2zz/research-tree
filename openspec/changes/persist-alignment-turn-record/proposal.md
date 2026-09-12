# Proposal: persist-alignment-turn-record

## Why

Issue #497: alignment state lives mainly in conversation context. The designed
persistence ("Persist an alignment-turn record after each meaningful exchange")
is SKILL prose with no writer, no reader-gate, and no hook refresh — so in a
long conversation (or after compaction) the agent's working model of the brief
silently decays. Within 3-4 turns it forgets earlier answers, drifts, and
begins self-asking / self-answering: it asks a question, then answers it
itself from stale context instead of waiting for the user. User ruling
(2026-09-02): 对齐表现要在 research-tree 文件里面体现；不写文件就无法更新 —
the alignment behavior must be reflected in a research-tree file; without
writing the file there is no update. ADR-008's canonical contract-emission
loop ends in "Persist (per #497) the turn-record with contract terms, traces,
and user-response class"; this change delivers that persistence step as a
first-class workspace artifact plus its fail-closed continuity gate.

## What Changes

1. `src/research_tree/alignment_turn_record.py` (NEW): the alignment
   turn-record persistence layer. Appends one JSON line per pre-handoff
   alignment turn to the run's alignment workspace file
   (`.research-tree/projects/<project_id>/runs/<run_id>/alignment/turn-records.jsonl`),
   following the workspace-artifact patterns of `project_workspace.py`.
   Record fields: `mirror` (current understanding), `gap` (named
   consequential gap), `delta` (what changed on the graph: summary + touched
   node ids), `user_move` (the classified user response class from the
   `turn_contract` seam's `RESPONSE_CLASSES`), plus `contract_terms` and
   `traces` carried with the seam module's schema (`ContractTerms`,
   `DEFAULT_TRACE_REGISTRY`, `verify_traces`) — reused, not duplicated.
2. Fail-closed continuity gate: `AlignmentTurnRecordStore.check_continuity()`
   refuses (named reasons) the next alignment turn when the record file is
   missing, unreadable/invalid, or stale (an earlier exchange never
   persisted). `append()` enforces the same adjacency, so a turn record can
   never be written out of order, and rejects a turn whose delta is empty —
   a turn that introduces no persisted delta is a protocol violation
   (the self-ask/self-answer guard).
3. Hook support in `src/research_tree/lifecycle_hook.py`: `UserPromptSubmit`
   and `PostToolUse` refresh and validate the record file (fail-open, never
   blocking the host session) and surface the verdict on the record result;
   a validation receipt is written next to the records so compaction or long
   sessions cannot silently orphan the file. Integration only — the #503
   research re-entry protocol (`reopen_alignment` / `supplemental_evidence` /
   `status_echo`) is untouched.
4. Prompt layer (canonical sources only): the SKILL prose "Persist an
   alignment-turn record … after each meaningful exchange"
   (`skill-src/SKILL.template.md`, `skill-src/hermes-SKILL.template.md`)
   gains the enforcement wording — record-or-block: load and ground in the
   persisted record before composing the move, append the record before
   responding, a missing/stale record blocks the turn, a turn with no
   persisted delta is a protocol violation. `packages/**` regenerated in a
   generated-only commit.
5. `tests/test_alignment_turn_record.py` and
   `tests/test_lifecycle_hook_turn_record.py` (NEW): the issue's scenarios —
   4+ turn conversation growth with grounded continuity, compaction /
   deleted / stale records blocking fail-closed after hook refresh, and the
   no-persisted-delta protocol-violation guard.

## Capabilities

### New Capabilities

- `alignment-turn-record`: per-turn file persistence of the pre-handoff
  alignment state (mirror/gap/delta/user-move + contract terms and traces)
  with a fail-closed continuity gate and lifecycle-hook refresh/validation.

### Modified Capabilities

- None. (`lifecycle-facade` behavior is unchanged: the hook stays fail-open;
  the turn-record refresh is additive observation.)

## Impact

- Additive: 1 new code module, 2 new test files, 1 new openspec change
  folder, prose edit in 2 canonical SKILL templates, regenerated
  `packages/**`.
- `src/research_tree/lifecycle_hook.py` is the only existing module modified:
  `observe` (GitNexus upstream impact LOW, 2 impacted — direct caller `main`
  + module `Research_tree`, 1 execution flow) and `_observe_prompt_signal`
  (LOW, 3 impacted — caller `observe` plus packaged mirrors). Existing #503
  re-entry tests (`tests/test_lifecycle_hook_reentry.py`) must keep passing.
- No changes to `alignment_graph.py` (owned by #491/#496),
  `decision_frame.py`, `tree_state.py`, `search_portfolio.py`,
  `cross_comparison.py`, `recursive_search.py`, `references/**`, or
  `turn_contract.py` (consumed read-only per ADR-008; the seam stays
  unwired — wiring the emission loop is #489/#490).
