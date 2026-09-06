# Design: emit-turn-contract

## Context

Issue #489 wires the two-layer contract (ADR-008, #504) into the alignment
controller. Everything it needs is merged: the seam (`turn_contract.py`:
`ContractTerms` / `CostCap` / `DEFAULT_TRACE_REGISTRY` / `verify_traces`),
divergence-aware state (#496: `divergence_axes`, per-node stagnation,
`DIALOGUE_MODES`), the score-gated exit (#491: `alignment_incomplete`),
per-turn records with a fail-closed continuity gate (#497:
`alignment_turn_record.py`), and the user-response policy table (#490:
`decision_frame.resolve_user_response_policy`, whose fed
`alignment_user_move` records were explicitly designed as "the input basis
#489 wires into emission").

The original issue direction (extend the engine action vocabulary with
clarify/exemplify/mirror/counterexample) is rejected; the engine never gains
behavior vocabulary. The controller output keeps its existing actions and
gains the emitted contract terms as the #489 layer.

## Goals / Non-Goals

**Goals:**

- `plan()` emits `contract_terms` — `target_gap` (ranked graph node),
  `required_traces` (finite names from the frozen registry), `cost_cap`
  (response-production ceiling), `taboos` (settled / ask-spent / stalled
  nodes) — and `user_move_policy` when a signal resolved.
- `record()` verifies recorded traces against the emitted terms and persists
  traces + the typed user move on the turn's event.
- The turn record (#497) carries terms + traces + user-move class per turn.
- The 13-candidate strategy list lands as prompt-layer craft material with an
  explicit rejected-design note.

**Non-Goals:**

- No new action vocabulary, no strategy selection in the engine, no
  content-quality gates (ADR-008: presence and schema only).
- No turn-shape metrics (#493), no `proportionality_assessment` trace type
  (#498), no transformation traces (#499) — later waves append to the
  registry additively.
- No engine-side rewriting of the turn-record JSONL: the record file stays
  owned by the turn protocol (#497); the graph verifies and persists to its
  own event log, and the canonical loop's persist step is the turn record
  append (tested end-to-end).

## The canonical four-step loop, wired

1. **Emit** — `plan()` builds the terms after choosing the decision
   (additive keys on the decision, persisted via the existing
   `last_decision_json`; `_materialize` is untouched):

   - `target_gap`: the graph's rank order (active-axis nodes first, then
     impact, then fewest asks — the existing `eligible` sort) filtered by the
     taboo set. The #490 verdict overrides per directive: `reopen` forces the
     corrected node back as target; `advance`/`redirect` take the verdict's
     resolved gap target (next candidate away from the answered/interrupted
     node); `keep` keeps the rank order. Fallbacks: top open requester-only
     gap by impact, then the node carrying the top open axis, then the
     strategy node.
   - `taboos`: recomputed from live state each plan — requester-only nodes
     that are settled (accepted statuses), whose `MAX_ASKS_PER_NODE` budget
     is spent without an active axis, or that are locally stalled
     (`MAX_STAGNANT_TURNS`) without an active axis — union the #490 verdict
     additions (e.g. the just-answered node), minus the verdict removals
     (the corrected node re-opens), minus the chosen target.
   - `cost_cap`: unbounded generation for open-ended elicitation
     (`ask_one`) and for non-asking decisions; the one-sentence
     discrimination cap for `await_human_confirmation` (a confirm is a point,
     not an essay). A resolved #490 verdict replaces it (correction lowers —
     generation/2, repeated correction discrimination/1, never raising an
     emitted cap; interruption/insight raise to unbounded generation); with a
     verdict that leaves the cap alone (answer/neutral), the previous
     emitted cap carries forward ("neutral keeps"), else the base rule.
   - `required_traces` (ask turns only; other decisions emit an empty gate):
     gap shape + response-production class →
     - misunderstood intent (node `disputed`, or a correction-driven
       `reopen`) → `guess-statement` (the turn must restate the corrected
       understanding);
     - proposal-shaped + discrimination cap → `option-set` (a pointing
       response requires the options be shown);
     - proposal-shaped + generation cap → `possibility-survey` (the space is
       surveyed before an open question).
     The "user profile" input is the engine-visible response-production
     class; novice/expert persona inference stays prompt-layer (#500).

2. **Compose** — prompt layer only. `references/alignment-craft.md` teaches
   the 13 candidate strategies the composer may combine against the terms;
   the engine never selects among them.

3. **Verify** — `record(..., traces=[...])` verifies BEFORE any state
   mutation via `turn_contract.verify_traces()` against the last plan's
   emitted terms; a missing required trace raises `MissingTraceError` naming
   the exact term. Legacy `record()` calls (no `traces` parameter) keep
   working unchanged — the additive-surface guarantee that keeps the existing
   suites green; the turn-record gate (#497) enforces the same terms at
   persist time for protocol participants.

4. **Persist** — the verified turn's event details carry the traces and the
   typed user move; the canonical persist step is the #497 turn-record
   append (`AlignmentTurnRecordStore.append(contract_terms=…, traces=…,
   user_move=…)`, which re-verifies fail-closed on read).

### The observed signal's transport

`plan()` reads the newest (and previous) `alignment_user_move` feed record
from the run's `events/` directory — the surface #490's hook plumbing already
persists — with a bounded, fail-open scan; newest = the current prompt's
classification, previous = the repeated-correction input. Explicit
`user_signal` / `previous_category` parameters override for direct callers.
The run root is resolved from the database location
(`…/runs/<run-id>/alignment/alignment.db`). No hook changes.

## Packaging

The packaged single-file controller ships beside bare-module fallbacks
(established idiom). `turn_contract.py`, `decision_frame.py`, and
`domain.py` (decision_frame's only local dependency, stdlib-only) are added
to COMMON_FILE_MAP and the Hermes executable closure (empty-arguments
entrypoints) so the packaged `alignment_controller.py plan` emits and
verifies the full loop in every host package; `packages/**` is regenerated
in a generated-only commit. Without the seam importable, the controller
degrades fail-open (no `contract_terms` emitted, verification skipped) —
the same contract the lifecycle hook already honors.

## impact_scope

Index rebuilt via `node .gitnexus/run.cjs analyze .` in the #489 worktree at
branch tip `4fbe239` (15,650 nodes / 31,959 edges) before any edit; impact
run upstream per touched symbol; detect-changes reconciliation stored in
`evidence/` before push.

| Symbol / file | Status | Risk | Upstream callers (from impact) |
|---|---|---|---|
| `alignment_graph.AlignmentGraphStore._materialize` | NOT modified (state projection unchanged) | **MEDIUM** (5 direct / 19 impacted) | plan/record/confirm/waive/status via `_commit_event`; emission rides existing `last_decision_json` — no schema change |
| `alignment_graph.AlignmentGraphStore` | additive methods/kwargs | LOW (3 direct / 11 impacted) | module-level wrappers, CLI main, tests |
| `alignment_graph.AlignmentGraphStore.plan` / `.record` | additive kwargs + output keys | callers resolve through the class (property-access limit noted by GitNexus): module wrappers, `scripts/alignment_controller.py`, CLI, ~15 test files | additive only; existing suites are the guardrail |
| `alignment_graph._emit_contract_terms`, `_emission_taboos`, `_gap_shape_required_traces`, `_base_cost_cap`, `_latest_user_move_feed`, `_previous_contract_terms` (new) | added | LOW (no upstream callers — new surface) | plan/record |
| `decision_frame.resolve_user_response_policy` | consumed read-only | LOW | emission + hook (unchanged) |
| `turn_contract.ContractTerms`, `verify_traces`, `MissingTraceError` | consumed read-only | LOW | emission/record |
| `decision_frame` domain-import fallback | packaging idiom, no behavior change | LOW | import graph only |
| `skill-src/SKILL.template.md`, `references/alignment-craft.md`, `scripts/build_skill_packages.py`, `scripts/hermes_executable_closure.json` | prompt layer + packaging registration | LOW | packages parity gate |
| `packages/**` | regenerated | LOW (generated) | parity gate |
| `tests/test_contract_emission.py` | added | LOW | pytest collection |

Blast-radius note (AGENTS.md MUST): `_materialize` is the state-projection
hub — this change deliberately does not touch it; the emission rides the
existing controller `last_decision` surface, so graph-digest meaning, event
replay, and rebuild paths are unchanged.

## Rejected Designs

- **Engine strategy vocabulary (the original #489 direction)**: rejected by
  the 2026-09-03 ruling — 13 actions would be 13 postures of the same
  interrogation; the enumerated space is contract terms and trace types only.
  The 13 candidates live in the craft reference with a note that they must
  never become engine enums or fixed selection ladders.
- **Making `record()` unconditionally gate on the last emitted terms**:
  rejected — it would break every legacy `record()` call site (the existing
  suites are an explicit additive-surface constraint). Verification engages
  when the caller participates in the protocol (passes `traces`); the #497
  record gate enforces the same terms at persist time.
- **Writing the turn-record JSONL from the graph store**: rejected — the
  record protocol is append-one-per-exchange by the turn loop with its own
  fail-closed continuity gate (#497); a second writer would fork ownership.
- **Expressing "possibility-survey OR option-set" as alternatives in the
  terms schema**: rejected — `verify_traces` is intentionally conjunction
  semantics; the derivation picks one deterministically from the emitted cap
  class instead of loosening the seam.
- **Persisting contract terms as new state in `_materialize`**: rejected —
  the terms are a property of the current ask, already persisted in the
  decision; new state-shape fields would change graph-digest inputs and the
  rebuild contract for zero added capability.
- **Accumulating previous taboos verbatim turn over turn**: rejected — stale
  entries would linger on reopened nodes; taboos are recomputed from live
  graph state each plan with the verdict as the delta.
- **New CLI flags for the signal on `alignment_controller.py record/plan`**:
  rejected for this change — the hook feed is the transport; direct callers
  use the store API. The CLI stays byte-compatible.

## Risks / Trade-offs

- [Highest-risk file in the milestone] -> additive-only edits, `_materialize`
  untouched, existing alignment suites run as regression guardrails, impact
  reconciliation in `evidence/` before push.
- [Feed-scan misordering] -> records carry fixed-width timestamp-prefixed
  names (established); a missed signal only degrades to rank-order emission
  (fail-open), never a wrong gate: verification is against the actually
  emitted terms.
- [Trace gate on ask turns could block a turn] -> fail-closed by design; the
  named-term failure tells the composer exactly which structural artifact is
  missing, and the next plan re-emits.

## Migration Plan

No data migration: additive output keys, additive keyword parameters with
defaults, unchanged state shape and schema. Runs recorded before this change
have no `contract_terms` on their last decision; emission starts at the next
plan and verification only engages for protocol participants.

## Open Questions

- None blocking.
