## ADDED Requirements

### Requirement: the user profile is a turn-context input

`plan()` accepts `user_profile` (novice/expert/absent) supplied by the SKILL
layer; the engine never infers it and rejects unknown values.

#### Scenario: unknown profile is rejected
- **WHEN** plan() is called with `user_profile: "genius"`
- **THEN** a value error naming `user_profile` is raised

#### Scenario: absent profile keeps current behavior
- **WHEN** plan() runs without a profile
- **THEN** emitted terms match the pre-#500 derivation exactly

### Requirement: novice-facing turns are show-then-point

For a novice profile the emitted terms force a discrimination cost cap, an
option-set trace, and a possibility-survey before anything open-ended.

#### Scenario: first novice ask carries survey and option set
- **WHEN** plan() runs with a novice profile on a gap with no recorded survey
- **THEN** required traces include `possibility-survey` and `option-set`, and the cap is discrimination

#### Scenario: recorded survey relaxes to option set
- **WHEN** a possibility-survey trace was already recorded for the target gap
- **THEN** required traces include `option-set` (no repeated survey)

#### Scenario: open question without a survey fails verification
- **WHEN** the recorded turn omits the required possibility-survey trace
- **THEN** record-time verification fails closed naming the missing term
