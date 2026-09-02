# Design: alignment-score-exit-policy

## Context

Issue #491: the turn cap (`MAX_TURNS = 6`, `alignment_graph.py`) is used as an
alignment-*exit*: at the cap `plan()` switches to `reconnaissance` and silently
abandons unresolved requester-only nodes, so runs rush into research with open
high-impact gaps. #505 (#496) landed the divergence-aware state model
(`divergence_axes`, per-node stagnation, `DIALOGUE_MODES`) and explicitly left
`MAX_TURNS` and the readiness branches untouched for this change. The exit
policy must stop being a turn counter and become an alignment property: exit
when alignment is achieved (score), block with a named, explicit disposition
when it is not, and let the *user* decide between extending the dialogue and
explicitly waiving.

## Goals / Non-Goals

**Goals:**

- On the turn cap: an explicit `alignment_incomplete` blocked disposition
  naming open high-impact gaps and exhausted-ask nodes — never a silent
  strategy switch.
- A deterministic, testable alignment score over #496 graph state gating the
  exit; score and threshold as named, documented constants.
- Escalation instead of abandonment for exhausted high-impact asks.
- A recorded explicit-waive path; without it, the below-threshold exit stays
  blocked even under user pressure.
- Contained blast radius: `_materialize` (CRITICAL hub) untouched; no schema
  change.

**Non-Goals:**

- #489 contract emission / #490 response classification / #497 turn-record
  persistence (`lifecycle_hook.py` is owned in parallel).
- Prompt-layer wording of the blocked disposition (SKILL prose is #489/#500).
- Replacing `_alignment_readiness`: it stays the hard structural gate
  (required types, oracles, track coverage); the score is the additional
  quality gate on top, not a loosening of readiness.
- Touching the #496 stalled-dialogue reconnaissance (stall-conditioned, and
  encoded by `tests/test_alignment_divergence.py`).

## impact_scope

Index rebuilt via `node .gitnexus/run.cjs analyze .` in this worktree at
branch tip `50621df` (15,156 nodes / 31,018 edges) before any edit; impact run
upstream per symbol; detect-changes reconciliation stored in `evidence/`
before push.

| Symbol / file | Status | Risk | Upstream callers (from impact) |
|---|---|---|---|
| `AlignmentGraphStore.plan` | modified | LOW (6 impacted) | module `plan` wrapper, CLI `main`; flows: main/plan |
| `AlignmentGraphStore.confirm` | modified | LOW (6 impacted) | module `confirm` wrapper, CLI `main` |
| `AlignmentGraphStore.record` | modified | LOW (6 impacted) | module `record` wrapper, CLI `main` |
| `AlignmentGraphStore.waive` | added | LOW | module `waive` wrapper, CLI `main`, tests |
| `AlignmentGraphStore._materialize` | **not touched** | CRITICAL (17 impacted) | unchanged by this change; score/waive derive from existing state + event log |
| module `_alignment_score`, `_active_waive`, `_extension_deadline`, `_escalation_nodes`, `_blocked_disposition` | added | LOW | `plan`, `confirm`, `record`, `waive` |
| module constants (`ALIGNMENT_SCORE_*`, `ALIGNMENT_HIGH_IMPACT`, `ALIGNMENT_EXTENSION_TURNS`, `MAX_TURNS` comment) | added/modified | LOW | module consumers |
| CLI `_parser` / `main` / module `waive` | modified | LOW | CLI users |
| `tests/test_alignment_exit_policy.py` | added | LOW | pytest collection |
| `packages/**` | regenerated | LOW (generated) | parity gate |

No symbol is renamed; no `find-and-replace` refactors are needed.

## Decisions

### One score, computed from #496 state

`_alignment_score(nodes, axes)` returns an integer 0..`ALIGNMENT_SCORE_MAX`
(100), starting at the maximum and subtracting deterministic penalties:

- `ALIGNMENT_SCORE_OPEN_GAP_WEIGHT` (20) per **impact point** (1–5) of an open
  requester-only gap (`human_only` candidate/disputed) — impact-weighted, so a
  P0 gap alone zeroes the score while a trivial gap costs little;
- `ALIGNMENT_SCORE_EXHAUSTED_ASK_WEIGHT` (10) per open requester-only gap whose
  `MAX_ASKS_PER_NODE` budget is spent — the ask-budget residue the issue names;
- `ALIGNMENT_SCORE_OPEN_AXIS_WEIGHT` (10) per **open** divergence axis (#496
  per-axis convergence state) — a user-raised direction nobody explored is an
  alignment gap even on an otherwise settled node, and this is exactly what
  makes the score gate bite on structurally-ready graphs.

The score is exact integer arithmetic (no float drift) and depends only on
materialized state, so it is byte-stable across reopens and rebuilds.

### Exit is score-gated; the turn cap only blocks

`plan()` decision order becomes:

1. readiness ready **and** exit allowed (`score >= ALIGNMENT_SCORE_EXIT_THRESHOLD`
   or a valid waive) → `await_human_confirmation` (the normal handoff path);
2. exit **not** allowed and `turn >= MAX_TURNS` and no extension window →
   `alignment_incomplete` (the blocked disposition);
3. eligible node exists (unchanged #496 eligibility) → `ask_one`;
4. exhausted high-impact requester-only gap exists → `alignment_incomplete`
   (escalation);
5. otherwise → the unchanged #496 reconnaissance branches (stall /
   agent-verifiable reasons).

Below threshold **without** the cap the dialogue simply continues (ask_one);
the cap never exits, it blocks and names the residue. `confirm()` gains the
same gate right after readiness: a below-threshold score without a waive
raises "alignment score N is below the exit threshold ..." — user pressure
cannot bypass it. With threshold = maximum, the gate adds no strictness beyond
readiness for open gaps (readiness already hard-blocks those); its new bite is
open axes and spent ask budgets, and the threshold is a named constant so the
product can tune the bar without re-encoding the policy.

### The blocked disposition names the residue

`_blocked_disposition(...)` builds:

```
{action: "alignment_incomplete", reason, question: None,
 alignment_score, alignment_exit_threshold,
 blocked_nodes: [{node_id, impact, asks_exhausted}, ...],   # every open requester-only gap, impact-desc
 exhausted_ask_nodes: [node_id, ...],                        # the MAX_ASKS_PER_NODE-spent subset
 open_axes: [description, ...],                              # unexplored user-raised directions
 requires: "extend the dialogue by answering, or record an explicit waive"}
```

`plan()` also returns additive `alignment_score` / `alignment_exit_threshold`
keys (next to the existing additive `readiness`), and `record()`
replaces `next_action: "reconnaissance"` with `"alignment_incomplete"` when
the dialogue mode is stalled **and** an exhausted high-impact gap exists — so
a caller following `record()`'s advice cannot bypass `plan()`'s escalation.

### Escalation, not abandonment (composes with #496)

`_escalation_nodes` = open requester-only gaps with
`ask_count >= MAX_ASKS_PER_NODE` and `impact >= ALIGNMENT_HIGH_IMPACT` (4,
matching the high-impact threshold already used by `_alignment_readiness`).
They escalate only when the dialogue has **no** other move (branch 4): while
another node is askable, #496's local-convergence isolation still applies
(keep exploring elsewhere), and an active axis on the exhausted node keeps the
node itself askable first (branch 3), so the axis-based extra allowance is not
foreclosed. Stalled-but-not-exhausted high-impact gaps keep the #496 behavior
(`test_full_stall_moves_to_reconnaissance_until_divergence_reopens` pins it:
the user went quiet on a point never asked — reconnaissance with the stall
reason is acceptable and the gap stays open in the graph).

### User extension = engagement after the block, bounded

A `response_recorded` event after the newest `alignment_incomplete`
`plan_selected` event grants `ALIGNMENT_EXTENSION_TURNS` (3) more dialogue
turns from that response's turn (`_extension_deadline`, derived from the event
log — no schema change). Within the window the normal decision order runs
(asking again); past it, the blocked disposition returns and a fresh user
response is required to extend again. Each extension is therefore an explicit
user choice, and the cap can never silently end the dialogue.

### Explicit waive, bound to graph content

`AlignmentGraphStore.waive(reason)` rejects empty/generic acknowledgements
(same bar as `confirm`), records an `alignment_waived` event carrying the
reason (plus its digest), the current `graph_digest`, the score, the threshold
and the named open gaps — the audit record the issue's "explicit waive"
requires. `_active_waive` accepts the newest such event only while its
`graph_digest` equals the current one: any graph change (merge or a state-
changing record) invalidates the waive and the gate re-engages. Both the CLI
(`waive --run-id ... --reason ...`) and the store API are surfaced.

### No schema change; `_materialize` untouched

Waive and extension state live in the existing append-only event log
(`details_json`); the score derives from materialized state `plan()` /
`confirm()` / `record()` already load. `SCHEMA` stays 3, `_materialize`
(CRITICAL, 17 impacted) is not modified, and `graph_digest` semantics are
untouched (the waive binds *to* the digest rather than entering it).

## Rejected Designs

- **Keeping a turn-based exit with a bigger budget** (raise `MAX_TURNS`): the
  issue's root cause is budget-bounded alignment quality, not the number 6;
  any constant re-creates the rush, just later.
- **Replacing readiness with the score** (single gate): readiness encodes
  structural requirements `compile_handoff` depends on (oracles, tracks,
  evidence anchors); folding them into a score would make handoff acceptance
  fuzzy and break `confirm`'s contract. Two gates compose: structural AND
  quality.
- **Threshold below the maximum to allow low-impact gaps through**: the issue
  asks for user decisions, not silent leniency; with a lower threshold the
  agent would still silently exit over residue the user never saw. Leniency
  belongs to the explicit waive, which names what is being waived.
- **Persisting waive/extension in new controller columns** (schema bump): the
  event log already records decisions immutably and the derive-on-read cost is
  trivial at dialogue scale; a schema bump would invalidate every existing
  alignment database for no querying need.
- **A new `plan()` action enum value** beyond `alignment_incomplete`
  (e.g. `explore_axis`): same rejection as #496 — consumers match on the
  existing action set; `alignment_incomplete` is the one new disposition the
  issue names, everything else reuses existing actions/fields.
- **Weighing stagnation into the score**: stagnation is a *pace* signal
  (already governing eligibility and dialogue mode in #496), not an alignment
  *completeness* signal; a quiet user answering everything may be fully
  aligned while a chatty one may not. Mixing the two would make the score
  nondeterministic w.r.t. dialogue pacing.
- **Silent "agent-verifiable" reconnaissance on the cap** (status quo): the
  exact behavior the issue forbids — human-only gaps cannot be settled by
  evidence, so resolving "remaining nodes with evidence" was always abandonment.

## Risks / Trade-offs

- [_materialize is the CRITICAL hub] -> not touched: score/waive derive
  outside it; detect-changes reconciliation before push must show no
  `_materialize` hunks.
- [Score gate makes an unexplored axis on a settled node block handoff] ->
  intended (that is the "no patience" failure); the dialogue explores the axis
  first (generalized axis eligibility: any node with an active axis is
  askable), and the waive path exists for users who decline.
- [Known corner: two `plan()` calls within one turn] -> an active-axis node
  asked this turn is not re-eligible (`last_asked_turn` guard, which also
  keeps ask_count honest), so the second call falls through to the
  stall/agent-verifiable branch; self-corrects on the next record. Accepted;
  the lifecycle calls `plan()` once per turn.
- [Event-log scan for the extension window] -> bounded by dialogue-scale event
  counts and indexed by `event_type` filters; details/state JSON parsed only
  for the newest block and the first post-block response.
- [Generated packages carry the new engine copy] -> regenerated in a
  generated-only commit via `build_skill_packages.py`; parity gate enforced.

## Migration Plan

No data migration: `SCHEMA` stays 3 and no stored shape changes. Old runs
reopened under the new code gain the score gate immediately; a run already
past handoff confirmation (`autonomous`) is unaffected (`plan()` is not
consulted there). Consumers that matched the removed turn-cap
`reconnaissance` decision must now handle `alignment_incomplete` — within the
repo, only tests reference the turn-cap behavior, and none of them encodes it
(audited below).
