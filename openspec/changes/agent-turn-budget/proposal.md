# Proposal: agent-turn-budget

## Why

issue #527 (confirmed, recurring user feedback): the agent asks three-to-five
questions in one breath and dumps several thousand characters per turn. The
user-side `cost_cap` has always bounded the requester's response cost; the
agent's own output has no budget. Worse, the contract machinery itself drives
long turns: `required_traces` can demand several structural artifacts in a
single turn, so the composer's rational move is to stuff everything into one
turn. The #514 turn-shape gate measures the result but is flag-not-block and
has no contract term behind it.

## What Changes

1. `AgentTurnBudget` (turn_contract.py, additive): `max_questions = 1` per
   interactive turn and `max_chars` per turn (tier-settable by #526; default
   constant 1200). Carried as an optional `ContractTerms.agent_turn_budget`
   field — emitted WITH the contract terms, verified at record time like
   traces. Legacy terms without the new fields still parse (schema additive).
2. Required-trace queueing: the emission composes a priority-ordered
   wishlist (carried deferrals first, then gap-shape and novice-posture
   requirements), emits at most 2 as `required_traces`, and carries the
   remainder in the emitted terms as `deferred_traces`; the next turn's
   terms re-emit them as required. Nothing is silently dropped.
3. Record-time verification (alignment_graph.py record region): a recorded
   turn exceeding `max_questions` or `max_chars` is a named violation —
   flag-not-block (the turn stays valid as continuity grounding) — returned
   as `turn_budget_violations` in the record result and the persisted event
   details, structured (`dimension` / `limit` / `observed`) so the
   discipline-telemetry issue #525 can count it.
4. Question budget: asks consume the per-turn question budget (visible in
   the decision's `question_budget` disposition); when exhausted, `plan()`
   emits a non-question decision (the mirror/teach/gather postures, using
   the existing action vocabulary) until `record()` advances the turn and
   resets the budget. Per-node `MAX_ASKS_PER_NODE` stays; this is per-TURN.
5. Overrun semantics are split-not-truncate: the deferral queue plus the
   next emission carry the remainder; repeated violations feed #525's ladder.

## Impact

- src/research_tree/turn_contract.py: additive `AgentTurnBudget`,
  `deferred_traces` / `agent_turn_budget` optional `ContractTerms` fields
  with backward-compatible parsing; no breaking change.
- src/research_tree/alignment_graph.py: contract-emission region (budget
  attachment, trace queueing, question-budget disposition) and record()
  result/event region (budget verification); localized diff.
- tests/test_agent_turn_budget.py: new scenario tests.
- No canonical skill prose touched; packages not regenerated (parity check
  runs as a gate).
