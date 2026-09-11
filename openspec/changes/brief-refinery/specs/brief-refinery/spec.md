## ADDED Requirements

### Requirement: extraction yields atomic clustered typed objects with conservative defaults

The engine MUST validate model-produced candidate atoms against a strict
whitelist schema (statement, anchors, topic, polarity, requested type,
equivalence keys) and MUST reject malformed atoms fail-closed. Every
extracted object MUST start as `preference` or `environment-claim` — never
`hard-constraint`; a candidate requesting `hard-constraint` MUST be
downgraded to `preference`. Equivalent atoms (same normalized statement or
a shared equivalence key, clustered through the claims.py union-find
surface) MUST merge into one object; merged-away objects MUST record
`merged_into` and the surviving object MUST absorb their anchors.

#### Scenario: multi-statement brief extracts to typed non-blocking objects
- **WHEN** a candidate atom requests type `hard-constraint` and the extraction is applied
- **THEN** the registered object carries type `preference`, and no extraction path
  ever registers a `hard-constraint` object

#### Scenario: equivalent candidates merge into one object
- **WHEN** two candidates in one extraction share an equivalence key
- **THEN** the registry holds one live object, the merged-away object carries
  status `merged` with `merged_into` naming the survivor, and the survivor's
  anchors contain the merged-away object's anchors

#### Scenario: malformed candidate rejected fail-closed
- **WHEN** a candidate atom misses a required field or carries an unknown type value
- **THEN** the extraction raises a schema error naming the offending candidate and
  registers nothing from that batch

### Requirement: lifecycle transitions are enforced fail-closed

The registry MUST enforce the lifecycle `open → clarified / parked /
dropped / merged` with `parked → open` reactivation; `clarified`,
`dropped`, and `merged` MUST be terminal. An illegal transition MUST raise
an error naming the rejected transition and leave the object unchanged.

#### Scenario: illegal transition rejected naming the transition
- **WHEN** an object in state `open` is transitioned to `open`, or a terminal
  object is transitioned at all
- **THEN** the registry raises an illegal-transition error naming both endpoints
  and the object keeps its prior status

#### Scenario: parked reactivates to open
- **WHEN** a parked object is transitioned to `open`
- **THEN** the transition succeeds

### Requirement: hard-constraint upgrade requires a confirmation reference

`confirm_hard_constraint` MUST require a non-empty confirmation reference
(a recorded trace/dialogue anchor) and MUST refuse the upgrade without one.
Only the confirmation path MUST produce a `hard-constraint` object.

#### Scenario: upgrade refused without a confirmation reference
- **WHEN** `confirm_hard_constraint` is called with an empty, whitespace, or
  missing confirmation reference
- **THEN** the registry raises a confirmation-required error and the object
  keeps its type

#### Scenario: upgrade with a reference records the confirmation
- **WHEN** `confirm_hard_constraint` is called with a valid reference
- **THEN** the object carries type `hard-constraint` and the reference is
  persisted on the object

### Requirement: conflict pairs are detected deterministically

The engine MUST detect conflict pairs deterministically: two live objects
with the same normalized topic and opposite polarity are one conflict pair.
Conflict counting MUST be a pure registry query.

#### Scenario: opposing polarity on one topic forms a conflict pair
- **WHEN** the registry holds two live objects with topic `offline-support`
  and polarities `positive` and `negative`
- **THEN** `conflicts()` returns 1 and the pair names both object ids

### Requirement: vagueness and conflict queries return registry-derived numbers

`vagueness()` MUST return the share of live objects (not dropped, not
merged) whose status is still `open` or `parked`; `conflicts()` MUST return
the live conflict-pair count. Both MUST be computable from the persisted
registry alone.

#### Scenario: vagueness reflects unresolved share
- **WHEN** four live objects exist and one is clarified
- **THEN** `vagueness()` returns 0.75

### Requirement: registry persists engine-written with digest and fails closed

The registry MUST persist as engine-written JSON under the run's
`alignment/` directory with a SHA-256 digest over the object state; loading
MUST verify the digest and MUST fail closed on schema or digest mismatch.

#### Scenario: persistence round-trip preserves objects and digest
- **WHEN** a populated registry is saved and loaded from the same run root
- **THEN** the loaded registry has identical objects and an identical digest

#### Scenario: tampered registry fails closed on load
- **WHEN** a saved registry file is edited outside the engine
- **THEN** loading raises a registry error naming the digest mismatch and no
  objects are returned

### Requirement: only confirmed hard-constraint violations become closure blockers

The registry MUST expose a closure-blocker query that names violations of
**confirmed** `hard-constraint` objects only (same normalized topic,
opposite polarity). Unconfirmed objects MUST never appear as blockers. The
query is additive — nothing in this change wires it into closure gates.

#### Scenario: unconfirmed constraint never blocks
- **WHEN** an observation opposes a `preference` object (even one that
  requested hard-constraint at extraction)
- **THEN** `closure_blockers` returns no blocker for it

#### Scenario: confirmed hard-constraint violation names a blocker
- **WHEN** an observation opposes a confirmed `hard-constraint` object
- **THEN** `closure_blockers` returns a blocker naming the object id and the
  opposing observation

### Requirement: registry changes count as the turn-record delta

A helper on the turn-record module MUST convert a registry change set into
the delta payload (`summary`, `nodes`) that `AlignmentTurnRecordStore.append`
consumes; an empty change set MUST be refused.

#### Scenario: registry changes become the delta payload
- **WHEN** the helper receives a non-empty registry change set
- **THEN** it returns a summary naming the actions and node ids that satisfy the
  delta-node identifier rules
