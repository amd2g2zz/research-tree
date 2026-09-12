# Proposal: adaptive-stance

## Why

issue #526 (confirmed user feedback): during alignment the agent reads as
distrusting — anti-sycophancy mechanisms landed as "doubt the user by
default" (proportionality mandatory on every proposal-shaped gap,
zero-tolerance exit score). Undertrust is as much a calibration failure as
overtrust, and the user ruled the fix is NOT one static policy: all three
postures must exist and the level must move with observed signal — start on
trust, tighten when the user turns out not to know what they want, loosen as
clarity returns. Challenge must target the plan's risk, never the person.

## What Changes

1. `resolve_stance(clarity, vagueness, conflict, violation_rate, *,
   override=None)` in alignment_graph.py: deterministic, threshold-named
   mapping of the four measured signals (the #491 alignment score, the #524
   brief-registry open share, registry conflict pairs + #490 correction
   frequency, and the #525 sliding-window violation rate) onto the tiers
   S1 trust-first / S2 structured / S3 strict. S3 on conflict/error, S2 on
   high vagueness, S1 default; clarity at or above the recovery band (85)
   steps the tier back down; a validated explicit override beats the
   computed tier; out-of-range signals and unknown tiers are rejected.
2. `plan()` gains a `stance` param (declared by the SKILL layer like
   `user_profile`) and, when undeclared, computes the tier per turn from the
   run's own stores (fail-open to clean signals). The decision emits
   `stance` beside the contract terms (plus `stance_signals` when computed);
   the engine never infers the stance from user text.
3. Tier-shaped emission: S1 default-trust — proportionality is no longer
   unconditional on proposal shape; only a magnitude signal (impact ≥ 4 or
   a recorded over/under judgment) requires it. S2 reuses the #520 novice
   posture (show-then-point, discrimination floor, survey-before-open) and
   forces the gather turn when open divergence axes exceed
   `MAX_ACTIVE_AXES = 2` (an option set over the open topics, required
   ahead of the carried trace queue). S3 makes the challenges explicit
   (proportionality + counterargument as required traces on ask turns) and
   freezes divergence (`record()` refuses new axes in S3).
4. Tier-crossing invariants: the one-question-per-turn invariant stays a
   #527 flag in S1 but is a HARD record gate in S2/S3 (fail-closed before
   mutation); the axis concurrency bound holds via the gather duty (S2+).
5. Score transparency: the blocked disposition, the handoff decision, and
   the waive result carry `score_summary` — "understood ~85%; remaining: X"
   — so the waive reads as a mutual acknowledgment.

## Impact

- src/research_tree/alignment_graph.py: stance region (constants +
  `resolve_stance`), plan() stance resolution/gather branch (additive keys),
  record() invariant gates, `_gap_required_traces` signal-triggering,
  `_emit_contract_terms` S2/S3 shaping, `_blocked_disposition`/`waive`
  transparency; read-only consumption of brief_refinery (#524) and
  discipline (#525) queries behind a fail-open import seam. `_materialize`
  untouched.
- tests/test_adaptive_stance.py (new scenarios),
  tests/test_proportionality_trace.py (signal-triggered contract).
- skill-src templates: stance-awareness paragraph (budget-compressed).
- Generated packages: alignment_controller.py copies regenerated in a
  generated-only commit.
