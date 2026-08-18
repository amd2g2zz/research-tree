## ADDED Requirements

### Requirement: Activation is host-neutral and ordered

Codex, Claude, and Hermes SHALL use the ordered phases
`verified_load`, `bounded_reconnaissance`, `alignment_question`,
`explicit_handoff`, and `autonomous_dispatch`. A host SHALL NOT skip to
autonomous dispatch.

#### Scenario: Missing loader proof

- **WHEN** the loader state is missing, stale, or unavailable
- **THEN** activation is `blocked` with `loader_integrity_unverified`

### Requirement: Explicit handoff gates autonomous work

The activation gate SHALL require alignment equilibrium and an explicit
confirmed handoff before research, delegation, or dispatch. Ordinary answers,
small edits, and unrelated requests SHALL remain non-triggering.

#### Scenario: Implicit acknowledgement

- **WHEN** the user has not explicitly confirmed the handoff
- **THEN** the gate returns `blocked` and no autonomous action is authorized

### Requirement: Activation failures are bounded

The activation system MUST ensure missing resources, unavailable tools,
provider/context failures, and incomplete alignment return a stable blocked or
unavailable disposition naming the
failed phase and safe next action. They MUST NOT produce a final research
artifact.

#### Scenario: Provider context failure

- **WHEN** a required provider or context budget is unavailable during
  activation
- **THEN** the host records `blocked` or `unavailable` and does not dispatch or
  write a final research artifact
