# Alignment Turn Craft — composing against contract terms

This file is prompt-layer teaching material for the agent that *composes* an
alignment turn. It is explicitly NOT engine vocabulary: the engine emits
contract terms and verifies structural traces (`turn_contract.py`); everything
on this page is craft the composer may combine freely. Read it together with
`references/alignment-controller.md`.

## The loop you are composing inside

Each alignment turn, the controller (`alignment_controller.py plan`) emits
contract terms next to its decision:

- `target_gap` — the one alignment-graph node this turn must advance;
- `required_traces` — the structural artifacts the turn must produce (from a
  finite registry: option-set, concept-card, guess-statement, counterargument,
  possibility-survey, evidence-delta);
- `cost_cap` — how much production the user's next response costs
  (`discrimination` ≤ one-sentence point/confirm; `generation` allows free
  text, possibly sentence-bounded);
- `taboos` — nodes already answered or whose ask budget/stall budget is
  spent; do not re-ask them.

Compose the turn against those terms, record the turn's traces with the turn
record (mirror, gap, delta, user move, contract terms, traces), and the
engine verifies the required traces exist — presence and schema only, never
content quality. A missing trace fails naming the exact term: produce that
artifact, don't argue with the gate.

## The candidate strategies

Thirteen composing patterns recur in good alignment dialogue. They are a
palette, not a menu: combine, adapt, or invent — selection is yours, made
fresh each turn from the terms and the dialogue so far.

- **echo-guess** — restate your best guess of the requester's intent in your
  own words and let them correct it. Serves a `guess-statement` trace; ideal
  after a correction or on a disputed point (misunderstood-intent gaps).
- **example-anchor** — ground an abstract dimension in one concrete worked
  instance from their world. Pairs with open questions; keeps vague briefs
  attachable.
- **constraint-menu** — lay out the binding constraints (not options) so the
  requester can react to the shape of the space rather than choose blindly.
  A rare structured turn; never a substitute for open-ended guidance.
- **possibility-survey** — survey the possibility space around the gap before
  asking about it. Serves a `possibility-survey` trace; the default companion
  to an open question on a proposal-shaped gap.
- **teach-then-verify** — teach the smallest concept the requester is missing,
  then verify by asking them to apply it. Serves `concept-card` traces; the
  remedy for confusion or missing vocabulary.
- **open-question** — one open-ended, guided prompt answered in their own
  words. The workhorse for proposal-shaped gaps under a generation cap.
- **mirror** — reflect the current understanding back (beliefs, scope,
  tensions) so drift is visible. Cheap, powerful after any new material.
- **reconnaissance** — leave the dialogue briefly and inspect web, repository,
  or supplied sources so the next turn adds knowledge the requester lacks.
  The controller's `reconnaissance` decision means now is the time.
- **counterargument** — present the strongest case against the current
  direction. Serves a `counterargument` trace; use when agreement feels
  unearned.
- **proportionality-challenge** — test whether the effort matches the stakes:
  name the cheaper path or the deeper obligation the request implies.
- **consequence-warning** — state concretely what goes unmet if the current
  course holds (which oracle, which contradiction). Use before complying with
  an insistence, never as a substitute for it.
- **ask** — the explicit question itself, exactly one per turn. Every
  elicitation turn ends in one; the contract's `target_gap` is its subject.
- **await** — when the decision is `await_human_confirmation`, display the
  compact strategy projection and stop: the next move is the requester's
  one-sentence confirmation carrying the displayed digest.

## How terms shape composition

- A `guess-statement` requirement is a signal the last turn misread the
  requester: echo-guess or mirror first, ask second.
- `possibility-survey` / `option-set` requirements are structural floors, not
  ceilings: the survey or option set must exist as an artifact, and the turn
  may still carry an open question around it.
- A `discrimination` cost cap means the user will point, not write: show the
  options (option-set) and make each one distinguishable in a sentence.
- A `generation` cap invites their words: ask open-ended and stop talking.
  A sentence-bounded generation cap means model your own turn so their answer
  fits the budget.
- `taboos` are settled or spent: advance to the named `target_gap` instead of
  circling back.

## Rejected design — this page is not an engine

The thirteen strategies above must never become engine enums, required
actions, or a fixed selection ladder. The 2026-09-03 architecture ruling
(ADR-008) is deliberate: enumerating behavior in the engine just replaces one
rigid template with several — thirteen actions would be thirteen postures of
the same interrogation. The engine's only enumerated spaces are the contract
terms and the trace-type registry; flexibility comes from free composition at
generation time. If a turn needs a sixteenth pattern, compose it — no engine
change is needed, and none is allowed to be required.
