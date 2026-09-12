## ADDED Requirements

### Requirement: tree state carries a gated run phase

The research-tree state payload SHALL support an explicit `phase`
discriminator naming one of intake, alignment, compiled, research,
validation, or delivery. A tree state written through the canonical service
SHALL default to `compiled` when the phase is omitted, SHALL reject any
other birth phase at initialization, and SHALL reject a transition whose
successor phase is not in the gated successor set of the previous phase
(previous phase defaulting to `compiled` for legacy payloads). Unknown phase
values SHALL be rejected by the payload validation.

#### Scenario: a compiled tree is born compiled

- **WHEN** a research tree is initialized from a confirmed handoff
- **THEN** the persisted state records phase `compiled` and the service
  accepts the revision

#### Scenario: a payload claims an illegal transition

- **WHEN** a transition payload claims any successor outside the gated graph
  (for example `research → delivery`, `alignment → research`,
  `validation → research`, `intake → research`, or any transition out of
  `delivery`)
- **THEN** the transition is rejected with a named illegal-transition error
  and no artifact is appended

#### Scenario: an unknown phase value is rejected

- **WHEN** a payload carries `phase` set to a value outside the six run
  phases
- **THEN** the payload validation rejects the state

#### Scenario: legacy payloads remain readable

- **WHEN** a persisted payload predates the phase field
- **THEN** validation accepts it, `tree_phase_of` reports `compiled`, and
  its next transition is gated as if the previous phase were `compiled`

### Requirement: post-compile strategy changes require user realignment

A tree-state payload MAY carry `strategy_authority_fingerprint` (the
confirmed projection's authority fingerprint) and a `realignment` record
binding a fresh user confirmation digest to a new authority fingerprint. A
transition that changes the recorded fingerprint SHALL be rejected unless it
is the recompile edge out of re-entered alignment AND carries a valid
realignment record whose authority fingerprint equals the payload's
fingerprint; the record SHALL be structurally valid (schema 1, 64-hex
confirmation digest, 64-hex authority fingerprint, non-empty bounded reason)
and bound to the payload's fingerprint. Dropping the recorded fingerprint
outside that edge SHALL be rejected.

#### Scenario: silent strategy mutation is rejected

- **WHEN** a transition payload changes `strategy_authority_fingerprint`
  without a realignment record (for example on a research self-loop or
  `compiled → research`)
- **THEN** the transition is rejected with a named realignment-required
  error and no artifact is appended

#### Scenario: realignment recompiles with a fresh fingerprint

- **WHEN** the run re-enters alignment (via `compiled → alignment` or
  `research → alignment`) and the recompiled state changes the fingerprint
  with a valid `realignment` record binding the new fingerprint to a fresh
  confirmation digest
- **THEN** the `alignment → compiled` transition is accepted

#### Scenario: a realignment record that does not bind the fingerprint is rejected

- **WHEN** a payload carries a realignment record whose authority
  fingerprint differs from the payload's `strategy_authority_fingerprint`,
  or a malformed digest, schema, or empty reason
- **THEN** the payload validation rejects the state

### Requirement: research-phase interruptions resolve through the two-option protocol

When the run phase is `research`, the lifecycle hook SHALL resolve every
user prompt to exactly one re-entry path — `reopen_alignment` (re-align to
user confirmation, recompile) or `supplemental_evidence` (record the input
and stay in research) — with `status_echo` as the only acceptable status
interaction, and SHALL refuse every other prompt (including chatty
conversational drift and bare interruptions that pick no path) with the
named code `research_reentry_refused`. The resolution SHALL be persisted on
the signal record and routed to the run's events surface. The phase source
SHALL be fail-open: an explicit valid argument, `RESEARCH_TREE_RUN_PHASE`,
or the run manifest's `phase` key, and an absent or invalid source leaves
the gate inactive; the hook SHALL never block the host session.

#### Scenario: an interruption picks reopen alignment

- **WHEN** the user interrupts during research asking to change the strategy
  or realign
- **THEN** the signal record names `reopen_alignment` and the run events
  surface receives the routed resolution

#### Scenario: an interruption supplements the running research

- **WHEN** the user interrupts during research providing new evidence,
  sources, or material
- **THEN** the signal record names `supplemental_evidence` and the run stays
  in research

#### Scenario: conversational drift is refused

- **WHEN** a research-phase prompt matches none of the protocol paths
  (chatty drift, or a bare interruption such as "stop" that picks no path)
- **THEN** the resolution is `refused` with code `research_reentry_refused`
  and the refusal is recorded; only the two protocol paths plus status echo
  are ever accepted

#### Scenario: the gate is inactive outside research and fail-open on bad input

- **WHEN** the resolved phase is absent or not `research`, the phase value is
  invalid in the environment or manifest, or no run is active
- **THEN** prompts keep their existing signal classification without a
  re-entry verdict, and the hook records nothing that blocks the session
