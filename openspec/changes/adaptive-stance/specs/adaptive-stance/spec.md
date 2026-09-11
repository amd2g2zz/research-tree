## ADDED Requirements

### Requirement: the stance is resolved from measured signals with named thresholds

`resolve_stance(clarity, vagueness, conflict, violation_rate)` SHALL map
the four measured signals onto exactly one of S1 (trust-first), S2
(structured), S3 (strict): S3 when conflict is at or above its threshold
(registry conflict pairs plus recorded corrections) or the violation rate
is at or above its threshold, else S2 when vagueness is at or above its
threshold, else S1. Clarity at or above the recovery band SHALL step the
computed tier back down one level. Out-of-range signals and unknown tiers
SHALL be rejected.

#### Scenario: each tier is reached by its signals

- **WHEN** the controller resolves stances from clean signals, from a
  vagueness at or above 0.5, from a conflict at or above 2, and from a
  violation rate at or above 0.4
- **THEN** the results are S1, S2, S3, and S3 respectively, and the S1
  boundary cases just below each threshold resolve to S1

#### Scenario: recovered clarity steps the tier back down

- **WHEN** clarity is at or above the recovery band (85) while an
  escalation signal persists
- **THEN** an S3 computation reads S2 and an S2 computation reads S1;
  below the band the escalation holds

#### Scenario: out-of-range signals are rejected

- **WHEN** any signal is outside its range (clarity outside 0..100,
  vagueness or violation rate outside 0.0..1.0, a negative conflict)
- **THEN** `resolve_stance` raises naming the offending signal

### Requirement: the user-side explicit override beats the computed tier

An explicit override SHALL be honored as an input: a validated override
value is returned regardless of the computed tier, and an unknown override
SHALL be rejected — both in `resolve_stance` and in the plan-level `stance`
declaration. The engine never infers the stance from user text.

#### Scenario: the override wins in both directions

- **WHEN** signals resolve to S3 but the override declares S1, and when
  signals resolve to S1 but the override declares S3
- **THEN** the declared tier is the emitted stance in each case

#### Scenario: an unknown tier is rejected before any mutation

- **WHEN** plan() is called with a stance outside the tier vocabulary
- **THEN** an error naming the allowed tiers is raised and no state changes

### Requirement: the turn stance is emitted beside the contract terms

When plan() runs without a declared stance, it SHALL compute the tier per
turn from the run's own stores (alignment score, brief-registry vagueness
and conflict pairs plus correction frequency, discipline violation rate),
fail-open to clean signals; the decision SHALL carry `stance` (and
`stance_signals` when computed). A declared stance SHALL suppress the
computation.

#### Scenario: the computed stance rides the decision

- **WHEN** plan() runs with no declared stance against a run whose brief
  registry is fully unresolved
- **THEN** the decision carries `stance: S2` and the four observed signals

#### Scenario: a declared stance skips the computation

- **WHEN** plan() is called with an explicit stance while computed signals
  would resolve higher
- **THEN** the emitted stance is the declared one and `stance_signals` is
  absent

### Requirement: S1 trusts ordinary input by default

In S1, a proposal-shaped gap SHALL NOT require the proportionality
assessment by shape alone: the assessment requires a magnitude signal — a
high-impact assertion (impact at or above the high-impact bar) or a
recorded over/under judgment. S1 declares axes without chasing them: no
gather duty fires.

#### Scenario: an ordinary proposal is not strip-searched

- **WHEN** an impact-3 proposal-shaped gap is asked in S1
- **THEN** the required traces are exactly the shape-class trace
  (possibility-survey, or option-set under a discrimination cap) with no
  proportionality assessment

#### Scenario: a magnitude-conflict proposal still requires the assessment

- **WHEN** a gap carries impact at or above 4 or a recorded over/under
  direction
- **THEN** the proportionality assessment is required even outside S3

### Requirement: S2 owns the structure and forces the gather turn

In S2, the emission SHALL reuse the #520 novice posture (discrimination
floor, option set, survey before anything open-ended), and when open
divergence axes exceed the concurrency bound of 2, plan() SHALL emit a
gather turn — a non-question decision with the open topics as the option
material — whose terms require `option-set` under the discrimination floor.

#### Scenario: axis overflow forces the gather action

- **WHEN** three divergence axes are open and the stance is S2
- **THEN** the decision is a gather turn (question absent,
  `gather_options` naming all three) and the terms require exactly
  `option-set`

#### Scenario: S1 keeps recording axes without the duty

- **WHEN** three divergence axes are open and the stance is S1
- **THEN** the decision stays an ask (no gather)

### Requirement: S3 surfaces the challenges and freezes divergence

In S3, ask turns SHALL carry the proportionality assessment and the
counterargument as explicit required traces (the #527 queue applies), and
`record()` SHALL refuse new divergence axes naming the freeze.

#### Scenario: an S3 ask turn requires the explicit challenges

- **WHEN** an ordinary proposal-shaped gap is asked in S3
- **THEN** the required traces include the proportionality assessment and
  the counterargument (deferred via the queue beyond two per turn)

#### Scenario: new axes are frozen in S3

- **WHEN** a response is recorded with new axes while the outstanding plan
  declared S3
- **THEN** the record is refused before any mutation and nothing persists

### Requirement: the one-question invariant is a hard gate in S2 and S3

In S2 and S3, a recorded turn exceeding the question budget SHALL be
refused fail-closed before mutation; in S1 the #527 flag-not-block behavior
is unchanged.

#### Scenario: two questions in one S2 turn are refused

- **WHEN** a turn is recorded with two questions while the outstanding
  plan declared S2
- **THEN** the record raises naming the stance gate and the turn index is
  unchanged

### Requirement: the alignment score is user-visible at the decisions

The blocked disposition, the handoff decision, and the waive result SHALL
carry `score_summary` — "understood ~N%; remaining: X" with the named
remaining gaps — so the waive reads as a mutual acknowledgment.

#### Scenario: the blocked disposition names the remaining gaps

- **WHEN** the turn budget is exhausted below the exit threshold
- **THEN** the disposition's `score_summary` starts with "understood ~"
  and names every open gap

#### Scenario: the waive carries the mutual acknowledgment

- **WHEN** a waive is recorded against an incomplete graph
- **THEN** the result carries the score summary naming the blocked nodes
