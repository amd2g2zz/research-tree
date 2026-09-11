## 1. Tests (RED first)

- [ ] 1.1 RED: budget carried in emitted terms; >1 question flags the
      `max_questions` dimension; over-length turn flags `max_chars`
- [ ] 1.2 RED: required traces capped at 2 with priority order, remainder
      deferred in the terms, deferred traces re-emitted as required next turn
- [ ] 1.3 RED: budget exhaustion forces a non-question decision with the
      question-budget disposition; legacy terms without budget fields parse

## 2. Implementation

- [ ] 2.1 turn_contract.py: `AgentTurnBudget` + named defaults + additive
      `ContractTerms.agent_turn_budget` / `deferred_traces` with
      backward-compatible parsing
- [x] 2.2 alignment_graph.py emission region: budget attachment, trace
      queueing (≤2 required, `deferred_traces` carry + re-emission),
      question-budget disposition and non-question decision
- [x] 2.3 alignment_graph.py record region: `question_count` / `turn_chars`
      measurements, `turn_budget_violations` in result + event details

## 3. Gate

- [x] 3.1 full suite + ruff + validate + governance + parity → PR
      feat/issue-527-agent-turn-budget → dev (do not merge)
