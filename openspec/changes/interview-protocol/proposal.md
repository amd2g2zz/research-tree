# Proposal: interview-protocol

## Why

issue #500 (design-philosophy level): the alignment flow is built as
interrogation — a rigid 5-state pipeline, 74 prohibitions, and a single
question-shaped guidance primitive assume an articulate user; a novice is
derailed within three turns (agent 把引导简单理解为提问). Per the 2026-09-03
design ruling: the fix is NOT a bigger menu of moves — flexibility comes from
generation-time composition under the #501 contract; the engine gates
structural traces, the prompt layer carries the interview craft.

## What Changes

1. **Engine**: `plan()` accepts a `user_profile` turn-context input
   (novice/expert, set by the SKILL layer from conversation signals — never
   inferred in engine code). For a novice profile the emitted contract terms
   force the interview posture: a `discrimination` cost cap (pointing, not
   free text), an `option-set` in required traces (show-then-point), and a
   `possibility-survey` requirement until one is recorded for the target gap
   (an open question without a prior survey cannot pass verification).
2. **Prompt layer** (canonical sources): the state machine keeps its
   sequence but gains the interview posture; the "ask one open-ended guided
   prompt" primitive is replaced by profile-aware ownership of the
   conversation — show-then-point for novices, open-ended co-evolution for
   experts, need decomposition as a first-class move, and guidance forms
   (structure/examples/constraint-options/echo-guess) as craft.
3. Packages regenerated (generated-only commit).

## Impact

- alignment_graph.py: one additive validated parameter, one event-log
  helper, one derivation branch. Existing behavior unchanged when the
  profile is absent (expert default).
- skill-src templates + references: prose only.
- No new trace types, no new state, no schema changes.
