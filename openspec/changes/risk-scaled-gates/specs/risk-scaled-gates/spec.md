## ADDED Requirements

### Requirement: closure blocker subsets scale by slot priority

`evaluate_research_stop` SHALL attach closure blockers to each slot
according to the slot's `priority`: a P0 slot SHALL carry the full blocker
set (coordinator assessment, independent evidence floor, validation oracle,
shallow source depth, mechanism artifacts, frontier remnants); a P1 slot
SHALL carry only the coordinator assessment, evidence-floor, and
validation-oracle blockers; a P2 slot SHALL carry only the evidence-floor
and validation-oracle blockers. The shallow-depth, mechanism, and
frontier-coverage computations and the mandatory drill-down scheduler SHALL
remain unconditional (producers stay intact); the subset selection only
filters which produced blockers attach to the slot's `closure_blockers`.
`evaluate_research_stop` SHALL NOT itself set a slot to `closed` at any
priority.

#### Scenario: a P2 slot closes without landscape, mechanism, or coverage blockers

- **WHEN** a P2 slot with a required validation oracle has its evidence floor
  met, its oracle passed, and a shallow-depth source that schedules a
  mandatory drill-down
- **THEN** the slot's `closure_blockers` is empty: no shallow-source-depth,
  mechanism-artifact, frontier-remnant, or coordinator-assessment blocker
  attaches, and the drill-down node is still scheduled (producer intact)

#### Scenario: a P0 slot keeps the full blocker set

- **WHEN** a P0 slot is evaluated in the same shallow-source situation
- **THEN** the slot's `closure_blockers` names the shallow source depth and
  the remaining frontier actions, and does not offer the coordinator
  assessment while those stand (regression pin of today's behavior)

#### Scenario: a P1 slot runs the middle blocker set

- **WHEN** a P1 slot with a required validation oracle is evaluated before
  evidence accrues and again after the floor is met and the oracle passes
- **THEN** the blockers are exactly the evidence-floor and validation-oracle
  blockers first, and exactly the coordinator-assessment blocker once both
  are satisfied — never a landscape, mechanism, or coverage blocker

#### Scenario: a P1 slot can opt back into the landscape gates

- **WHEN** a P1 slot declares `landscape_gates: true` and ingests a
  shallow-depth source
- **THEN** the shallow-source-depth blocker attaches exactly as it does for
  P0, and the compiled slot records the opt-in

### Requirement: recursive search config scales by task profile

`RecursiveSearchConfig` SHALL accept `profile` with exactly the values
`small`, `standard`, and `deep` (default `standard`), and SHALL reject any
other value at construction. The profile SHALL default `minimum_evidence`,
`max_depth`, and `transition_budget` to documented profile magnitudes —
`small` (1, 3, 16), `standard` (2, 5, 64 — today's constants), `deep`
(3, 8, 128) — and an explicitly passed field SHALL win over its profile
default. The evidence floor used by slot closure evaluation SHALL come from
the resolved config, so `small` lowers and `deep` raises the independent
evidence floor for every priority's subset.

#### Scenario: profile defaults load

- **WHEN** `RecursiveSearchConfig` is constructed with `profile="small"`,
  default (no profile), and `profile="deep"`
- **THEN** the resolved `minimum_evidence`/`max_depth`/`transition_budget`
  are (1, 3, 16), (2, 5, 64), and (3, 8, 128) respectively, and the config
  round-trips through its serialized form

#### Scenario: unknown profile is rejected

- **WHEN** `RecursiveSearchConfig(profile="huge")` is constructed
- **THEN** a `ValueError` naming the unknown profile is raised

#### Scenario: the profile scales the evidence floor at evaluation time

- **WHEN** a P2 slot with a passed oracle ingests one independent finding
  under `profile="small"` and the same state is evaluated under the standard
  profile
- **THEN** the small-profile evaluation presents no evidence-floor blocker
  while the standard-profile evaluation still reports insufficient evidence

### Requirement: irreversible gates never scale with priority

The authority fingerprint gate, the tree phase-transition gate, the
digest-bound deliverable-quality review, and evidence strict mode SHALL
ignore slot priority entirely: no priority weakens, skips, or bypasses them,
and this never-scaling list SHALL be recorded in the change design (ADR).

#### Scenario: never-scaling gates still fire on a P2-only tree

- **WHEN** a tree whose only slot is P2 has a passing quality review bound to
  stale report digests, an independent-verification payload with a malformed
  authority fingerprint, and an illegal phase transition proposed
- **THEN** the stale review is rejected as stale, the malformed fingerprint
  is rejected, and the illegal phase transition is rejected — none of the
  three gates consults the slot priority
