# Proposal: alignment-score-exit-policy

## Why

Issue #491 (bug, user report 2026-09-02: agent 迫不及待进入调研阶段, "没有耐心"):
turn-budget truncation is used as an alignment-exit mechanism. When the turn
counter hits `MAX_TURNS = 6`, `plan()` switches strategy to `reconnaissance`
("alignment dialogue limit reached; resolve remaining nodes with evidence") and
silently abandons every unresolved requester-only node — so runs rush into
research with open high-impact gaps. Relatedly, `MAX_ASKS_PER_NODE = 2` simply
stops a node from being eligible after two asks with no escalation path: an
exhausted high-impact point is abandoned by the same silent exit. Alignment
quality ends up bounded by a fixed dialogue budget instead of by alignment.

## What Changes

1. **Turn-cap escape removed.** Reaching `MAX_TURNS` no longer produces a
   `reconnaissance` decision. It produces an explicit blocked disposition
   `alignment_incomplete` that names the open requester-only gaps (with their
   impact and whether their ask budget is spent), the open divergence axes,
   and the alignment score versus the exit threshold — and requires the user
   to either extend the dialogue (by answering) or record an explicit waive.
2. **Alignment score gates the exit.** A deterministic
   `_alignment_score(nodes, axes)` (0..`ALIGNMENT_SCORE_MAX`) is computed from
   the #496 state model: impact-weighted open requester-only gaps, spent ask
   budgets on open gaps, and open divergence axes. Exiting the dialogue
   (handoff offer in `plan()`, acceptance in `confirm()`) requires
   `score >= ALIGNMENT_SCORE_EXIT_THRESHOLD` or a recorded waive. All score
   weights and the threshold are named, documented module constants.
3. **Escalation, not abandonment.** When every dialogue move is exhausted and
   an open requester-only gap has spent its ask budget at high impact
   (`ALIGNMENT_HIGH_IMPACT`), `plan()` returns `alignment_incomplete` naming
   it instead of the stall/agent-verifiable reconnaissance; `record()`'s
   `next_action` agrees. This composes with #496's axis-based extra ask
   allowance (an active axis still keeps the node askable first).
4. **User extension is real.** A user response recorded after a blocked
   disposition re-opens the dialogue for `ALIGNMENT_EXTENSION_TURNS` further
   turns (derived from the event log, no schema change); when the window is
   spent and the score is still below threshold, the blocked disposition
   returns and a fresh response is required.
5. **Explicit waive path.** `AlignmentGraphStore.waive(reason)` records an
   explicit user waive (generic acknowledgements rejected, same bar as handoff
   confirmation) as an `alignment_waived` event bound to the graph digest at
   waive time; the graph changing afterwards invalidates it. A valid waive
   lets `plan()` offer and `confirm()` accept the handoff despite a
   below-threshold score; without it the exit stays blocked.
6. Engine-side only: no SKILL prose changes; `packages/**` regenerated
   mechanically in a generated-only commit.

## Capabilities

### New Capabilities

- `alignment-exit-policy`: the score-gated alignment exit contract — the
  deterministic alignment score, the `alignment_incomplete` blocked
  disposition, the escalate-not-abandon rule for exhausted high-impact asks,
  the user-extension window, and the explicit waive path.

### Modified Capabilities

- None. `alignment-dialogue-state` (#496) is untouched; the turn-cap branch it
  deliberately left in place is the subject of this change.

## Impact

- `src/research_tree/alignment_graph.py` (owned file): module constants,
  `AlignmentGraphStore.plan` (decision order + score gate + blocked
  disposition), `AlignmentGraphStore.confirm` (score gate),
  `AlignmentGraphStore.record` (`next_action` escalation override),
  new `AlignmentGraphStore.waive`, new module helpers (`_alignment_score`,
  `_active_waive`, `_extension_deadline`, `_escalation_nodes`,
  `_blocked_disposition`), CLI `waive` subparser and module-level `waive`
  wrapper. GitNexus impact (index rebuilt at branch tip 50621df, 15,156
  nodes / 31,018 edges): `plan` LOW (6 impacted), `confirm` LOW (6),
  `record` LOW (6); `_materialize` is **CRITICAL** (17 impacted) and is
  **not touched** — the score and waive state are derived from existing
  materialized state plus the event log, so the state projection hub is
  unchanged. `SCHEMA` stays 3 (no new tables/columns; waive and extension
  state live in the existing event log).
- `tests/test_alignment_exit_policy.py` (new): one test per issue scenario.
  Existing alignment tests keep passing; none of them encodes the removed
  turn-cap reconnaissance escape (the #496 stalled-dialogue reconnaissance is
  a different, stall-conditioned branch and is preserved — see design.md).
- Out of scope: #489 (contract emission wiring), #490 (response
  classification), #497 (turn-record persistence, parallel owner of
  `lifecycle_hook.py`), SKILL prose / `skill-src/**` / `references/**`;
  `packages/**` only mechanically regenerated (generated-only commit).
