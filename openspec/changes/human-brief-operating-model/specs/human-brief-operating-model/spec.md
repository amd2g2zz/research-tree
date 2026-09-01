## ADDED Requirements

### Requirement: Human Brief exposes the operating model

The compiled Human Brief SHALL expose an operating-model block with an
exact-key schema (schema 1) carrying roles, outcome layers, blockers, a
fallback plan, and the three baseline-run dimensions (sla, concurrency_limits,
adoption_metrics). Every runtime-fed field SHALL be sourced from the run's own
artifacts — never hand-filled — and validation SHALL be fail-closed with
named-field errors.

#### Scenario: Brief without the operating-model block is rejected

- **WHEN** a Human Brief payload document lacks the `operating_model` key
- **THEN** payload validation raises, naming the missing key

#### Scenario: Baseline-run dimensions carry no commitments

- **WHEN** the operating model is compiled for a run with no measured SLA,
  concurrency, or adoption baseline yet
- **THEN** `sla`, `concurrency_limits`, and `adoption_metrics` are present
  with `basis: baseline_run` and `commitments: null`, labeled as measured
  baselines rather than commitments

### Requirement: Roles name the three operating roles and their handoff surfaces

The operating model SHALL name exactly the three operating roles (research
owner, platform integrator, governance auditor) with a non-empty
responsibility and handoff surface for each, using wording consistent with the
closed origin vocabulary. An operating model that names a different number of
roles SHALL be rejected.

#### Scenario: Operating model with a wrong number of roles is rejected

- **WHEN** the operating model lists two roles
- **THEN** validation raises, naming the expected three roles
- **WHEN** a role entry names an unknown role
- **THEN** validation raises, naming the allowed role vocabulary

#### Scenario: Rendered brief shows the roles

- **WHEN** the Human Brief markdown is rendered
- **THEN** the Roles section names the three roles with their responsibilities
  and handoff surfaces

### Requirement: Blockers mirror why_not_complete with owners and resolution conditions

The blocker list SHALL mirror the coordinator's `why_not_complete` resolve
entries verbatim (for example `resolve:goal_satisfaction:<oracle_id>`), each
with an owner role from the closed owner vocabulary (research_owner,
platform_integrator, governance_auditor, human_requester). Acceptance
obligations SHALL route to the human requester; all other obligations SHALL
route to the research owner. When the coordinator has no state for the run,
the blocker list SHALL say so explicitly (coordinator_state) instead of
claiming an unblocked run.

#### Scenario: Uncovered oracle appears as a blocker

- **WHEN** a success oracle has no current goal_satisfaction registration at
  delivery time
- **THEN** the blocker list contains `resolve:goal_satisfaction:<oracle_id>`
  owned by the research owner
- **WHEN** the acceptance obligation is unmet
- **THEN** the blocker list contains `resolve:acceptance_ref` owned by the
  human requester

#### Scenario: No coordinator state is disclosed, not hidden

- **WHEN** the coordinator has no run state for the run
- **THEN** the blocker list contains a `coordinator_state` entry whose
  resolution action names the conflict and directs the requester to re-enter
  alignment

### Requirement: Outcome layers resolve from real run artifacts

The outcome layers SHALL present three layers from the run's own artifacts:
the confirmed projection (id, revision, display digest, and the #450 authority
fingerprint) when one resolves; current per-oracle `goal_satisfaction`
verdicts (satisfied | partial | unmet | waived, with the waiver reason when
waived); and per-slot contribution summaries (latest per finding pack). A run
with no confirmed projection SHALL show the top layer as explicitly absent
(fail-closed), never as satisfied.

#### Scenario: Layers summarize a run with verdicts

- **WHEEN** the run has a confirmed projection, a satisfied oracle verdict,
  and a slot contribution
- **THEN** the outcome layers show the projection with its display digest and
  authority fingerprint, the verdict with its oracle id, and the slot
  contribution summary

#### Scenario: Run without a confirmed projection fails closed

- **WHEN** no confirmed projection resolves for the run
- **THEN** the top outcome layer is explicitly absent (null), and the brief
  never claims outcome confirmation it cannot trace

### Requirement: Fallback plan uses the availability-gate wording

The fallback plan SHALL give an understandable degraded path per capability,
using the availability-gate wording ("when the checkout runtime is
available"), consistent with the skill contract. An operating model with an
empty fallback plan SHALL be rejected.

#### Scenario: Unavailable host capability has a degradation path

- **WHEN** a host capability (Codex, Claude Code, Hermes) is unavailable
- **THEN** the fallback plan names the capability with an understandable
  degraded path that records a blocker instead of inferring success
