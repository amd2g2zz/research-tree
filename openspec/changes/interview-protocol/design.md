# Design: interview-protocol

## Approach

The engine already emits contract terms and verifies traces (#489). The
interview protocol is a *profile-aware emission policy* plus a prompt-layer
craft rewrite — exactly the #501 split.

### Profile as turn-context input

`plan(..., user_profile=None)` accepts `None | "novice" | "expert"`.
Validation rejects unknown values (fail-closed naming the field). The
SKILL layer sets it from conversation signals; the engine never infers it
(profile inference is open-ended natural-language judgment — prompt layer).

### Novice emission policy

When `user_profile == "novise"` — spelling aside, `"novice"` — the emitted
terms change three ways for ask turns:

- `cost_cap` is forced to the discrimination floor (`max_sentences = 1`):
  a novice points, they do not compose.
- `option-set` joins `required_traces`: the turn must show concrete options
  with examples (rejection-friendly).
- until a `possibility-survey` trace is recorded against the target gap
  (checked from the append-only `response_recorded` event log), the survey
  is prepended to `required_traces` — the first novice-facing turn must map
  the possibility space ("do X through an agent" → AI-plays / AI-assists /
  AI-generates) before anything open-ended. The #489 record-time
  verification makes an open question without a prior survey a named gate
  failure.

Expert profile and absent profile reproduce today's behavior exactly.

### Prompt layer

The interrogation primitive "Ask one open-ended, guided prompt at a time"
becomes profile-aware conversational ownership; guidance forms
(structure/examples/constraint-options/echo-guess) are craft material, and
need decomposition is a first-class move. No primitive menus, no ladder
rules — composition stays free inside the emitted terms.

## impact_scope

- `AlignmentGraphStore.plan` / module `plan` (additive validated parameter)
- `_emit_contract_terms` (profile branch), new `_gap_surveyed`
- skill-src/SKILL.template.md, skill-src/hermes-SKILL.template.md,
  references/research-quality-playbook.md, regenerated packages
- tests/test_interview_protocol.py (new)

## rejected_designs

- **Engine profile inference** (heuristics over user text): open-ended
  judgment belongs to the prompt layer (#501); the engine takes the profile
  as an input and gates structure only.
- **Fixed primitive menus / response-cost ladders** (#500 design ruling):
  13 primitives would be 13 postures of interrogation; composition is
  generated, not selected.
- **Blocking novice turns entirely until a survey exists**: the survey is
  *required of the current turn* (the verification gate), not a hard block —
  the composer satisfies it by presenting the possibility space.
- **A separate novice pipeline**: one pipeline, profile-aware emission;
  two pipelines would fork maintenance and drift.
