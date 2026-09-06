# Design: emit-turn-contract

## Context

Issue #489 wires the two-layer contract (ADR-008, #504) into the alignment
controller. Everything it needs is merged: the seam (`turn_contract.py`),
divergence-aware state (#496), the score-gated exit (#491), per-turn records
with a fail-closed continuity gate (#497), and the user-response policy table
(#490) — whose fed `alignment_user_move` records were designed as "the input
basis #489 wires into emission". The original issue direction (engine action
vocabulary) is rejected; the engine never gains behavior vocabulary.

## Goals / Non-Goals

**Goals:** `plan()` emits `contract_terms` (target_gap / required_traces /
cost_cap / taboos) plus `user_move_policy` when a signal resolved;
`record()` verifies recorded traces and persists traces + typed user move;
the #497 turn record carries terms + traces + user move; the 13-candidate
strategy list lands as prompt-layer craft material with a rejected-design
note.

**Non-Goals:** no new action vocabulary or strategy selection in the engine;
no content-quality gates (ADR-008: presence and schema only); no turn-shape
metrics (#493), `proportionality_assessment` (#498), or transformation traces
(#499); the graph never writes the #497 record file (turn protocol owns it).

## The canonical four-step loop, wired

1. **Emit** — `plan()` builds the terms after choosing the decision
   (additive keys on the decision, persisted via the existing
   `last_decision_json`; `_materialize` is untouched):

   - `target_gap`: the graph's rank order (active-axis nodes first, then
     impact, then fewest asks — the existing `eligible` sort, which now also
     excludes nodes whose latest recorded response was `answered`) filtered
     by the taboo set. The #490 verdict steers the candidate order itself:
     `reopen` forces the corrected node to the front, `advance`/`redirect`
     take the verdict's resolved gap target, `keep` keeps rank order.
     Fallbacks for non-asking decisions: top open requester-only gap by
     impact, node carrying the top open axis, strategy node, top node.
   - `taboos`: recomputed from live state each plan — requester-only nodes
     that are already answered (latest recorded outcome), whose
     `MAX_ASKS_PER_NODE` budget is spent without an active axis, or that are
     locally stalled (`MAX_STAGNANT_TURNS`) without an axis — union verdict
     additions, minus verdict removals, minus the chosen target.
   - `cost_cap`: unbounded generation for open-ended elicitation
     (`ask_one`) and non-asking decisions; the one-sentence discrimination
     cap for `await_human_confirmation`. A resolved #490 verdict replaces it
     (correction lowers and never raises; interruption/insight raise);
     answer/neutral keep the previous emitted cap.
   - `required_traces` (ask turns only): gap shape + response-production
     class → misunderstood intent (disputed target, or a correction-driven
     reopen) → `guess-statement`; proposal-shaped + discrimination cap →
     `option-set`; proposal-shaped + generation cap → `possibility-survey`.
     The "user profile" input is the engine-visible response-production
     class; novice/expert persona inference stays prompt-layer (#500).

2. **Compose** — prompt layer only (`references/alignment-craft.md`).

3. **Verify** — `record(..., traces=[...])` verifies BEFORE any state
   mutation via `turn_contract.verify_traces()` against the last plan's
   emitted terms; a missing required trace raises `MissingTraceError` naming
   the exact term. Legacy `record()` calls (no `traces` parameter) keep
   working unchanged — the additive-surface guarantee that keeps the existing
   suites green; the #497 record gate enforces the same terms at persist time.

4. **Persist** — the verified turn's event details carry the traces and the
   typed user move; the canonical persist step is the #497 turn-record
   append (`AlignmentTurnRecordStore.append`, which re-verifies fail-closed
   on read).

### The observed signal's transport

`plan()` reads the newest (and previous) `alignment_user_move` feed record
from the run's `events/` directory (resolved from the database location),
bounded and fail-open; newest = the current prompt's classification,
previous = the repeated-correction input. Explicit `user_signal` /
`previous_category` parameters override for direct callers. No hook changes.

## Packaging

`turn_contract.py`, `decision_frame.py`, and `domain.py` (decision_frame's
only local dependency, stdlib-only) join COMMON_FILE_MAP and the Hermes
executable closure so the packaged single-file controller emits and verifies
the full loop in every host package; `packages/**` is regenerated in a
generated-only commit. `decision_frame` gains the repository's
relative-then-bare import fallback idiom (packaging only). Without the seam
importable, the controller degrades fail-open (no terms emitted,
verification skipped) — the contract the lifecycle hook already honors.

## impact_scope

Index rebuilt via `node .gitnexus/run.cjs analyze .` in the #489 worktree at
branch tip `4fbe239` (15,650 nodes / 31,959 edges) before any edit; impact
run upstream per touched symbol; detect-changes reconciliation stored in
`evidence/` before push.

| Symbol / file | Status | Risk | Upstream callers (from impact) |
|---|---|---|---|
| `alignment_graph.AlignmentGraphStore._materialize` | NOT modified | **MEDIUM** (5 direct / 19 impacted) | state projection unchanged; terms ride existing `last_decision_json` |
| `alignment_graph.AlignmentGraphStore` | additive kwargs/output keys | LOW (3 direct / 11 impacted) | module wrappers, CLI main, tests |
| `AlignmentGraphStore.plan` / `.record` methods + module wrappers | additive | callers resolve through the class (property-access limit per GitNexus): module wrappers, `scripts/alignment_controller.py`, CLI, ~15 test files | additive only |
| new emission helpers (`_emit_contract_terms`, `_emission_taboos`, `_gap_required_traces`, `_base_cost_cap`, `_fallback_target`, `_user_move_signal_from_feed`, …) | added | LOW (no upstream callers) | plan/record |
| `decision_frame.resolve_user_response_policy` | consumed read-only (+ import fallback) | LOW | emission + hook |
| `turn_contract.ContractTerms`, `verify_traces` | consumed read-only | LOW | emission/record |
| `skill-src`, `references/alignment-craft.md`, build script, closure | prompt layer + packaging | LOW | packages parity gate |
| `packages/**` | regenerated | LOW (generated) | parity gate |
| `tests/test_contract_emission.py` | added | LOW | pytest collection |

Blast-radius note (AGENTS.md MUST): `_materialize` is the state-projection
hub — deliberately untouched; graph-digest meaning, event replay, and
rebuild paths are unchanged.

## Rejected Designs

- **Engine strategy vocabulary (the original #489 direction)**: rejected by
  the 2026-09-03 ruling — thirteen actions would be thirteen postures of the
  same interrogation; the enumerated space is contract terms and trace types
  only. The 13 candidates live in the craft reference with a note that they
  must never become engine enums or fixed selection ladders.
- **Unconditionally gating `record()` on the last emitted terms**: rejected —
  it would break every legacy call site (additive-surface constraint).
  Verification engages when the caller passes `traces`; the #497 record gate
  enforces the same terms at persist time.
- **Writing the turn-record JSONL from the graph store**: rejected — the
  record protocol is append-one-per-exchange by the turn loop (#497); a
  second writer would fork ownership.
- **OR-alternatives in the terms schema** ("possibility-survey OR
  option-set"): rejected — `verify_traces` is intentionally conjunctive; the
  derivation picks one deterministically from the emitted cap class.
- **Persisting contract terms as new `_materialize` state**: rejected — the
  terms are a property of the current ask, already persisted in the
  decision; new state-shape fields would change graph-digest inputs for zero
  added capability.
- **Accumulating previous taboos verbatim turn over turn**: rejected — stale
  entries would linger on reopened nodes; taboos recompute from live state
  with the verdict as the delta.
- **New CLI signal flags on `alignment_controller.py`**: rejected — the hook
  feed is the transport; direct callers use the store API.

## Risks / Trade-offs

- [Highest-risk file in the milestone] -> additive-only edits, `_materialize`
  untouched, existing alignment suites as guardrails, impact reconciliation
  in `evidence/` before push.
- [Feed-scan misordering] -> fixed-width timestamp-prefixed names
  (established); a missed signal degrades to rank-order emission (fail-open),
  never a wrong gate: verification is against the actually emitted terms.
- [Trace gate could block a turn] -> fail-closed by design; the named-term
  failure says which structural artifact is missing, and the next plan
  re-emits.

## Migration Plan

No data migration: additive output keys, additive keyword parameters with
defaults, unchanged state shape and schema. Pre-existing runs have no
`contract_terms` on their last decision; emission starts at the next plan
and verification only engages for protocol participants.

## Open Questions

- None blocking.
