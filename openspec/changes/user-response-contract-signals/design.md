# Design: user-response-contract-signals

## Context

Issue #490: the hook's five prompt-signal classes (`PROMPT_SIGNAL_CATEGORIES`
= correction / interruption / insight / answer / neutral) are persisted as
metadata only and never feed alignment policy; `ClarificationPolicy.evaluate`
reads only hypothesis dispositions; the controller's `plan()` ranks by
impact/ask_count. The agent cannot distinguish "user answered" from "user
redirected" from "user pushed back".

Three merged changes shape the starting point: #504 added the two-layer
contract seam (`turn_contract.py`: `target_gap` / `required_traces` /
`cost_cap` / `taboos`), #509 added per-turn records with a `user_move` field
(`alignment_turn_record.py`), #503 added run-phase discipline. The
2026-09-03 scope ruling (issue comment) shrinks the design space: contract
emission and trace verification are rule-governed bookkeeping, so the
realistic candidates are (a) a small policy table over contract-term
selection, (b) at most a bandit for cost-cap tuning, (c) a full MDP — and a
full MDP is expected to be over-engineered. #489 owns contract emission;
this change prepares its input basis.

## Goals / Non-Goals

**Goals:**

- The persisted user-response class is an input to contract-term selection:
  `cost_cap` adjustment from observed classes, `taboos` refresh (answered
  nodes become taboo; corrected nodes re-open), `target_gap` directive
  influenced by the last user move class.
- The classification output is typed onto the `turn_contract` seam's
  `RESPONSE_CLASSES` and lands on the surfaces that consume it: the
  alignment-turn-record `user_move` field (via the run-scoped signal feed
  the turn-record append path reads) and contract-term selection at the
  seam.
- A written strategy-selection comparison (policy table vs bandit vs full
  MDP) with a decision; rejected alternatives recorded below.
- Fail-open plumbing: the hook observes and feeds, never blocks.

**Non-Goals:**

- Rewiring the alignment controller's `plan()` or any action vocabulary
  (#489 owns contract emission; #496/#491 own the ranking/exit policy).
- Emitting contract terms into the graph (the verdict is the *input basis*;
  the emission wiring is #489).
- Learning/tuning from alignment-score deltas (deferred — see comparison).
- Prompt-layer prose (`skill-src/**`, `references/**`): the typed move is
  consumed engine-side; prose craft belongs to #500.

## Strategy-selection design comparison (issue #490 deliverable)

The open design question in the issue — "should strategy selection be
modeled as an MDP over interaction history?" — is answered here against the
post-#501 architecture, where the prompt layer composes turns freely and the
engine only emits contract terms and verifies traces. The decision surface
is exactly: which node is `target_gap`, how much response room `cost_cap`
grants, which nodes are `taboos`, which traces are `required_traces`.

### Option (a) — small policy table over contract terms (CHOSEN)

A deterministic, first-match-wins rule table mapping the observed signal
class (+ ask context, + one-step repetition) onto contract-term
adjustments. ~9 rows, each independently testable, every output auditable
from the persisted signal + verdict records.

- Fits the actual decision surface: contract-term selection *is*
  rule-governed bookkeeping (scope ruling). The state it needs is one step
  deep (last signal class, outstanding ask, previous class) — all persisted
  already.
- Deterministic and diagnosable: a wrong cap/taboo is traceable to a named
  rule; matches the repo's existing rule-table idiom
  (`PROMPT_SIGNAL_RULES`, `RESEARCH_REENTRY_RULES`).
- Zero new failure modes: no exploration, no state estimation, no reward
  wiring; fail-open degradation is trivial.

### Option (b) — bandit for cost-cap tuning (DEFERRED, rejected for beta1)

Treat each cost-cap level as an arm; reward = alignment-score delta per
exchange; update online.

- Premature: there is no feedback signal yet — contract emission is not
  wired (#489) and alignment-score deltas per exchange are not persisted as
  a reward stream. A bandit over a nonexistent reward channel would tune to
  noise.
- The actionable cap space is two classes × a bounded sentence budget — a
  bandit needs many pulls per arm to beat a sensible default, and each pull
  is a real user exchange (expensive, low-traffic regime).
- Deferral path is clean: the policy table's `cost_cap` rows are exactly
  the priors a bandit would need; when #489's emission produces per-exchange
  score deltas, a bandit can be layered *on top of* the table (table =
  default policy, bandit = tuned offsets) without reworking the seam.

### Option (c) — full MDP over interaction history (REJECTED)

State = (alignment graph delta, last user move class, hypothesis
confidences); action = policy vocabulary; reward = alignment-score delta.

- Wrong action space after #501: the engine no longer selects dialogue
  actions — the prompt layer composes them. An MDP over the old action
  vocabulary would re-enshrine the enumerated-behavior model ADR-008
  removed.
- State estimation is unsolvable with current artifacts: hypothesis
  confidences are not persisted per turn, graph deltas live in SQLite only
  when the reference flow runs, and reward (score delta) is unmeasured per
  exchange. An MDP over missing state is theater.
- Cost/benefit: a full MDP needs a reward model, transition data across
  hundreds of runs, and a policy solver — for a decision surface with two
  cap classes and four ranking directives. Massively over-engineered for
  beta1.

### Decision

Implement **(a) the small policy table** now. Record (b) and (c) as
rejected designs for this milestone: (b) is explicitly *deferrable* — its
preconditions (per-exchange reward channel via #489's emission) do not exist
yet, and the table is designed to be its prior; (c) is rejected outright —
the architecture it assumes (engine-selected dialogue actions) was removed
by ADR-008/#501. Revisit (b) only after #489 lands and real per-exchange
alignment-score deltas are observable.

## impact_scope

Index rebuilt via `node .gitnexus/run.cjs analyze .` in the #490 worktree at
branch tip `a2a81a0` (15,422 nodes / 31,576 edges) before any edit; impact
run upstream per touched symbol; detect-changes reconciliation stored in
`evidence/` before push.

| Symbol / file | Status | Risk | Upstream callers (from impact) |
|---|---|---|---|
| `lifecycle_hook._observe_prompt_signal` | modified | **LOW** (3 impacted) | `observe`; flow: main |
| `lifecycle_hook.observe` | reused, return path unchanged | **LOW** (2 impacted) | `main`; flow: main |
| `lifecycle_hook._feed_run_signal`, `_active_run`, `_resolve_run_phase` | reused read-only | **LOW** (3/6/4 impacted) | `_observe_prompt_signal` etc.; flow: main |
| `decision_frame.resolve_user_response_policy`, `UserMoveVerdict`, `USER_RESPONSE_*` (new symbols) | added | LOW (no upstream callers — new surface) | hook plumbing, tests |
| `turn_contract.*`, `alignment_turn_record.*` | consumed read-only | n/a | — |
| `tests/test_user_response_contract_signals.py` | added | LOW | pytest collection |
| `packages/**` | regenerated | LOW (generated) | parity gate |

No HIGH/CRITICAL blast radius. The modified hook symbol is LOW risk with one
direct caller; all seam/record modules are consumed read-only via their
public APIs.

## Decisions

### The policy table lives in `decision_frame.py`, additive

`decision_frame.py` is the requester-intent module; the classified user
response is requester-intent evidence. The table is a new, additive surface
(`resolve_user_response_policy` + `UserMoveVerdict` + vocabulary
constants) — `ClarificationPolicy`, `DecisionFrame`, and their schemas are
byte-for-byte unchanged. Rationale for not touching `ClarificationPolicy`:
the scope ruling moves the consumption point to **contract emission**
instead of action selection, and the clarification gate's actions
(`reconnaissance`/`ask_user`/`reframe`/`ready`) are a hypothesis-disposition
concern that must not drift with surface phrasing. Adding the table to a
new module was rejected to keep the change inside this issue's file
ownership and because the cohesion is real (both are "evidence-aware
requester intent").

The table reuses the seam's vocabulary — `turn_contract.RESPONSE_CLASSES`,
`turn_contract.CostCap`, `turn_contract.ContractTerms` — read-only, never
duplicated. The five signal categories are mirrored locally as
`USER_SIGNAL_CATEGORIES` (the hook's classifier stays the single
classification authority; consistency is pinned by a test).

### Rule rows (first match wins)

| # | Condition | user_move | cost_cap | taboos | gap directive |
|---|---|---|---|---|---|
| 1 | correction carrying continuation semantics (rule ends `+continuation`) | `generation` | unchanged | unchanged | `keep` |
| 2 | answer, ask outstanding (terms present) | `discrimination` | unchanged | + asked node | `advance` |
| 3 | answer, no ask | `discrimination` | unchanged | unchanged | `keep` |
| 4 | correction, repeated (previous signal for the run was also `correction`) | `generation` | → `discrimination`/1 (floor) | − asked node | `reopen` |
| 5 | correction, first | `generation` | → `generation`/2 (bounded) | − asked node | `reopen` (ask outstanding) else `keep` |
| 6 | interruption | `generation` | → `generation`/unbounded (raised) | unchanged | `redirect` |
| 7 | insight | `generation` | → `generation`/unbounded (raised) | unchanged | `keep` |
| 8 | neutral / no signal | `generation` | unchanged | unchanged | `keep` |

Semantics:

- **user_move typing** (feeds the turn-record field; #497 left the mapping
  to this change): `answer` is a pointing/confirming move →
  `discrimination`; every free-text move (correction, interruption, insight,
  neutral chatter) → `generation`.
- **cost_cap**: corrections lower the ceiling (mission example: "repeated
  corrections lower the response-production ceiling") — one correction
  bounds the next response to two sentences, a repeated correction drops to
  the one-sentence `discrimination` floor. Interruption/new material raises
  the ceiling to unbounded generation (room to receive the material).
  Answers and neutral turns leave the cap untouched.
- **Monotone guard (corrections only)**: a correction row never *raises*
  an emitted cap — if its computed cap is more permissive than the emitted
  one, the emitted cap is kept (a `discrimination`/1 emission stays at the
  floor). Interruption/insight rows intentionally raise the ceiling to
  unbounded generation (the maximum, so no guard is needed there); neutral
  and answer rows never touch the cap. No row can cause spurious drift.
- **taboos refresh**: an answered node becomes taboo and target-gap
  selection advances away from it (the asked node is the outstanding
  terms' `target_gap`); a corrected node is re-opened (taboo removal) and
  the directive returns to it.
- **gap directives**: `advance` / `reopen` / `redirect` / `keep`.
  `redirect` (interruption/new material) demotes the interrupted node — it
  stays open (not tabooed) — and resolves toward the next candidate from
  the caller-supplied candidate order (the graph's ranking, i.e. #489's
  emission input). Without candidates the verdict carries the directive
  only (`gap_target=None`); resolution is the caller's.
- **Continuation consistency** (row 1): a correction whose rule carries the
  `+continuation` suffix (the #453 downgrade for "…but continue with the
  plan") must not overturn anything — the requester kept the course.

### Plumbing: hook feeds the typed move and the verdict (fail-open)

In `_observe_prompt_signal`, when the resolved run phase is `alignment`
(#503 discipline: contract terms are an alignment-phase concept; during
research the re-entry protocol governs), the hook:

1. loads the latest turn record via `alignment_turn_record.
   AlignmentTurnRecordStore(run_root).latest()` (defensive import, consumed
   read-only — the store's existing public API, no schema changes) and uses
   its `contract_terms` as the ask context (None when absent);
2. reads the previous signal category for the same run from the bounded
   signals directory (newest matching record) for the repeated-correction
   row;
3. resolves `resolve_user_response_policy(signal, terms,
   previous_category=…)` and embeds the verdict on the record/result as
   `user_move_policy`;
4. feeds a routed copy of the record to the run's events surface with
   `route="alignment_user_move"` (the existing `_feed_run_signal`
   mechanism) — this is the persisted surface the turn-record append path
   reads for the `user_move` field and that #489's emission will consume
   for contract-term selection.

Every step is fail-open (missing module in standalone packaging, missing
run, unreadable store, invalid signal → no verdict, no feed, hook still
records the signal). `observe`'s return path, the #497 refresh, and the
#503 re-entry protocol are untouched; the hook never appends turn records
itself (one-record-per-exchange stays the turn protocol's property).

### The typed move is consumed, not just recorded

`(i)` the turn-record `user_move` field: the fed
`alignment_user_move` record carries the class in the seam's
`RESPONSE_CLASSES` vocabulary, so the append path records a typed move
instead of raw prompt prose categories; `(ii)` contract-term selection: the
fed record carries the `cost_cap`/`taboos`/`gap_directive` verdict computed
against the emitted terms — the input basis #489 wires into emission.
Nothing else consumes the classification (mission scope (iii)).

## Rejected Designs

- **Full MDP over interaction history** (issue's open question): rejected —
  see the comparison above. The architecture it presumes (engine-selected
  actions from a policy vocabulary) was removed by ADR-008/#501; its state
  (per-turn hypothesis confidences) and reward (per-exchange score delta)
  are not persisted; the decision surface (two cap classes, four ranking
  directives) does not need sequential optimization.
- **Bandit for cost-cap tuning**: rejected for this milestone, deferred
  with a clean layering path — no reward channel exists until #489 wires
  emission and per-exchange alignment-score deltas are persisted; the
  policy table's cap rows are the bandit's future prior.
- **Teaching `ClarificationPolicy.evaluate` the user move class**: rejected —
  the clarification gate's action vocabulary is hypothesis-disposition
  logic; letting surface phrasing steer it would re-couple intent framing
  to prompt wording (the exact statelessness the issue condemns, one level
  up). The scope ruling points consumption at contract emission instead.
- **Mapping the five signal classes into the turn-record `user_move` field
  verbatim**: rejected — the field's schema is the seam's
  `RESPONSE_CLASSES` (discrimination/generation); persisting the hook's
  category vocabulary there would fork the contract vocabulary ADR-008
  made the only enumerated space. The policy table performs the typed
  mapping instead (and the raw category stays on the signal record).
- **Letting the hook append/adjust turn records directly**: rejected — the
  record protocol is append-one-per-exchange by the turn loop with a
  fail-closed gate (#497); a fail-open observer writing records would break
  the protocol's ownership and the hook's never-blocks contract.
- **Storing the verdict in a new sidecar file**: rejected — the run events
  feed (`route` records) is the established run-scoped signal surface
  (#453); a new artifact would need its own continuity story for zero
  added capability.
- **Accepting an explicit "new material" node id in the signal**: rejected —
  the classifier is regex-prose-based and cannot name nodes; inventing node
  references from prose would fabricate graph identity. `redirect`
  demotes the current node and resolves toward the caller's candidate
  order instead (the graph owns node identity).

## Risks / Trade-offs

- [Regex classification is approximate] -> the policy only adjusts bookkeeping
  terms (cap, taboos, ranking directive), each recoverable next turn; the
  continuation-downgrade and confidence rows keep calibrated signals from
  over-adjusting; the monotone guard bounds worst-case drift.
- [Verdict computed against the latest record's terms, which may be absent]
  -> rows degrade deterministically without an ask (cap rows still apply,
  directive `keep`, no taboo changes); the emission wiring (#489) owns the
  no-terms case.
- [Repeat detection reads prior signal records] -> bounded scan of the
  capped signals directory, fail-open to `None` (row 5 then applies);
  a missed repeat only means a one-step-higher ceiling for one turn.
- [Generated packages carry the new hook code] -> regenerated in a
  generated-only commit via `build_skill_packages.py`; parity gate enforced.

## Migration Plan

No data migration: the verdict and feed are additive surfaces; existing
runs without alignment-phase prompts behave exactly as before. The
turn-record schema is unchanged (its `user_move` field already expects the
seam classes this change types). No API removals.

## Open Questions

- None blocking. Whether a bandit should later tune the cap rows is
  explicitly deferred (see comparison) and gated on #489's reward channel.
