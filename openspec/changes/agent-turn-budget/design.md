# Design: agent-turn-budget

## Approach

The contract terms (#513) are the single carrier: they gain the agent-side
budget the same way they already carry the user-side `cost_cap` — emitted
next to the decision, verified against the recorded turn, persisted in the
turn record. Flag-not-block everywhere: budget overruns are named, counted,
and split across turns; they never block a turn or the exit gate.

### AgentTurnBudget (turn_contract.py)

Frozen dataclass `AgentTurnBudget(max_questions, max_chars)` with positive
int validation and strict `to_dict`/`from_dict`. Named exported defaults:
`DEFAULT_MAX_QUESTIONS_PER_TURN = 1` (the one-question-per-interactive-turn
invariant behind the #514 shape gate's flag) and
`DEFAULT_MAX_CHARS_PER_TURN = 1200`. `ContractTerms` gains two optional
fields — `agent_turn_budget: AgentTurnBudget | None = None` and
`deferred_traces: tuple[str, ...] = ()` — validated like `required_traces`
(registered names, unique, disjoint from `required_traces`). Parsing stays
additive: `from_dict` accepts legacy five-key terms (missing optionals
default) and still rejects genuinely unknown keys; `SCHEMA_VERSION` stays 1
so every previously persisted decision parses (a bump would fail-open
existing runs' `previous_terms` to None and silently degrade cap carry and
record verification). #526 owns tier-setting the char budget; this change
ships the mechanism plus the default constants.

### Required-trace queueing (emission region)

`_emit_contract_terms` composes a priority-ordered wishlist: carried
deferrals from the previous terms first (oldest obligation first), then the
gap-shape requirements (`_gap_required_traces`, unchanged), then the #500
novice posture (the disputed/reopen `guess-statement` is no longer replaced
but kept — it is the misunderstood-intent floor). The first two names are
emitted as `required_traces`; the remainder are emitted as `deferred_traces`
and re-emitted as required by the next turn's terms (queue semantics, not
loss). Interactive non-question turns (the question-budget decision below)
participate in the same gate so the queue advances without asks; exit
(`await_human_confirmation`) and blocked decisions never carry a trace gate
so the requester's confirmation cannot fail on composition traces — their
terms carry the queue forward instead.

### Record-time budget verification (record region)

`record()` gains optional keyword-only `question_count` / `turn_chars`
measurements. When the persisted terms carry a budget, overruns are
returned as `turn_budget_violations` — a list of
`{"dimension": "max_questions"|"max_chars", "limit": N, "observed": M}` —
in both the record result and the persisted `response_recorded` event
details. The turn, its traces, and its continuity grounding remain valid
(flag-not-block, #514 ruling); #525 counts the structured entries.

### Question budget (decision selection)

Asks emitted this turn are read from persisted graph state (nodes with
`last_asked_turn == controller.turn`), so no schema change is needed. When
the count reaches the budget's `max_questions`, the eligible-gap branch
emits a non-question decision instead: existing action vocabulary, the
gap target and axis context kept, `question: None`, a reason naming the
mirror/teach/gather postures (prompt-layer craft vocabulary,
references/alignment-craft.md), and a `question_budget` disposition
(`max_questions` / `asked_this_turn` / `remaining`) on both ask and
budget-exhausted turns. `record()` advances the turn, which resets the
count. Per-node `MAX_ASKS_PER_NODE`, the escalation path, and the blocked
disposition are unchanged; repeated `plan()` calls inside one turn (the
#490 policy-application pattern) after the budget is spent no longer burn a
second node's ask.

## impact_scope

- `AgentTurnBudget`, `DEFAULT_MAX_QUESTIONS_PER_TURN`,
  `DEFAULT_MAX_CHARS_PER_TURN` (new, turn_contract.py)
- `ContractTerms` (additive optional fields), `AlignmentGraphStore.plan`
  (additive decision keys + budget-exhausted branch),
  `AlignmentGraphStore.record` (additive keyword parameters, additive
  result/event keys), `_emit_contract_terms`, `_gap_required_traces`
  (region-local), `_base_cost_cap` region helpers
- tests/test_agent_turn_budget.py (new)
- No skill prose; packages unchanged (parity gate must stay green)

## rejected_designs

- **Blocking or invalidating over-budget turns**: flag-not-block is the
  #514 ruling; the turn remains valid continuity grounding and the
  violation feeds #525's ladder instead of a gate.
- **Truncating over-budget output**: the issue orders split-not-truncate —
  the deferral queue and the next emission carry the remainder.
- **Bumping `SCHEMA_VERSION`**: previously persisted decisions would fail
  `from_dict` and degrade fail-open to no terms, silently dropping cap
  carry and record verification; additive optional parsing keeps them live.
- **A new decision action enum value** (e.g. `mirror`/`teach`): the engine
  decision vocabulary stays `{ask_one, reconnaissance,
  await_human_confirmation, alignment_incomplete}`; the postures are
  prompt-layer craft (per the #501 two-layer ruling) and are named in the
  decision's reason, not enumerated by the engine.
- **Deferring traces by dropping them silently at the cap**: queue
  semantics — the remainder rides in the emitted terms as
  `deferred_traces` and is re-emitted as required next turn.
- **Forcing the trace gate on exit/blocked turns**: the requester's
  confirmation response carries no traces; requiring composition artifacts
  there would block the #491 exit on composition quality.
- **Schema change to track asks-per-turn**: `nodes.last_asked_turn` already
  persists the ask turn; counting it needs no new column.
