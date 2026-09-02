# ADR-008: Two-layer contract — engine trace gates vs prompt-layer strategy

- Status: accepted (2026-09-03)
- Deciders: maintainer (root-cause architecture ruling, issue #501)
- Supersedes: none; amends ADR-002 (single completion authority) in scope only — the ruling constrains where behavior policy may live, not who emits completions

## Context

Several open issues (#489, #498, #499) were trending toward implementing
open-ended alignment behaviors as engine-side enumeration: new action
vocabulary entries, new checklist gates for qualities like "teaching" or
"expert judgment", fixed selection ladders over guidance moves. The
maintainer ruled on 2026-09-03 (issue #501): 通过词表肯定是无法覆盖的，很多
需要通过 prompt 来解 — a vocabulary cannot cover these behaviors; most must
be carried by the prompt. How to teach a novice, how to decompose an
ambiguous idea into a possibility survey, how to build show-then-point
option sets, how to construct a counterexample, tone and persona (冷静理性，
no flattery) are unbounded natural-language generation.

The evidence that the current split is wrong: the prompt layer is already
rich (SKILL 386 lines + ~1600 lines of references carry teaching cycles,
counterarguments, short-round discipline) yet none of it is enforced — every
"prose without gate" finding (#489, #493, #498) traces to missing engine-side
structural verification, not to missing prose. Meanwhile engine vocabulary
attempts (alignment_graph's node/ask bookkeeping, decision_frame's four
`POLICY_ACTIONS`) cannot express the behaviors the prose promises.

## Decision

Adopt the two-layer contract as the default architecture for all
alignment-domain behavior:

**Engine layer (runtime, verifiable)** gates ONLY on structural traces:

- State persistence and continuity gates (#497): turn records exist, the
  next turn grounds in them.
- Phase discipline and transitions (#492).
- Turn-shape measurement (#493): length, decision count.
- Composition checks (#499): transformation ratio, digest-first shape.
- Structural-trace gates: a possibility-survey artifact exists before
  open-question turns; a strategy display carries a counterargument field;
  each novice-facing turn carries options. The engine verifies *that a trace
  exists* (and that it is well-formed), never *what it says*.

**Prompt layer (SKILL.md + references, generative)** carries ALL open-ended
behavior strategy as craft guidance: interview craft, teaching, decomposing
ambiguous ideas into possibility surveys, building show-then-point option
sets, constructing counterexamples, persona. The prompt layer never pretends
its guidance is enforced; anything load-bearing gets an engine-side
structural gate instead.

**The contract-emission loop (canonical, per alignment turn):**

1. **Emit** structured contract terms for the next turn:
   - `target_gap` — the alignment-graph node this turn must advance;
   - `required_traces` — structural artifacts the turn must leave (finite
     set: option-set, concept-card, guess-statement, counterargument,
     possibility-survey, evidence-delta);
   - `cost_cap` — maximum user response production (bytes-to-decide, not
     bytes-to-read: 辨别类 ≤ 一句指认， 生成类才允许自由文本);
   - `taboos` — nodes already answered / asks already spent
     (`MAX_ASKS_PER_NODE` migrates here).
2. **Prompt layer composes** the turn: given terms + dialogue history + user
   profile, the model writes whatever serves the contract — it may teach,
   exemplify, echo-guess, combine three moves. Infinite generation space.
3. **Engine verifies** traces against terms; missing trace = gate failure
   with the named term (presence + schema only).
4. **Persist** (per #497) the turn-record with contract terms, traces, and
   user-response class (feeding #490's signal model).

**Design test** for any future proposal: *if it adds an enum entry for
something the model should say, it violates this contract; if it adds a
trace type the engine can verify, it conforms.* Contract terms and trace
types are finite and enumerable — that is the ONLY enumerated space.
Behaviors are infinite and generated — never enumerated.

The mechanical seam for this loop is `src/research_tree/turn_contract.py`
(contract-terms schema, frozen append-only trace-type registry,
`verify_traces()`), delivered unwired; #489/#490 own the rewiring of
`alignment_graph.py` / `decision_frame.py` / `lifecycle_hook.py` onto it.

## Rejected design

**Behavior enumeration in engine vocabulary.** Expanding the engine's action
menus (e.g. a 13-action table of echo-guess / example-anchor /
teach-then-verify / constraint-menu / possibility-survey /
proportionality-challenge / consequence-warning moves) or fixed selection
ladders over them is rejected. Enumerating behaviors as engine actions just
replaces one rigid template ("ask one question") with another ("execute a
template called teach") and cannot cover the generation space. Guidance-form
illustrations belong in prompt-layer craft docs as teaching material for the
composer; they must never become engine enums or fixed selection ladders.
Content-quality policing of trace payloads (regex or classifier) is rejected
for the same reason.

## Consequences

- Every alignment-domain issue (#489–#500) is re-split into engine-gate vs
  prompt-craft items against this contract; PR reviewers apply the design
  test as a rejected-design compliance check.
- New trace types (e.g. #498's `proportionality_assessment`) extend the
  registry append-only; existing entries are never redefined.
- Open-ended quality remains unverified by construction — the engine's
  silence about "how good" is the contract working, not a gap. Behavioral
  acceptance belongs to evaluation runs, not engine gates.
- `scripts/check_impact_scope.py` and the PR template carry the governance
  side: impact reports and detect-changes reconciliation are mandatory PR
  checklist items so engine-layer changes stay inside their declared scope.
