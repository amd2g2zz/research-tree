## ADDED Requirements

### Requirement: Intent hypotheses are persistent and evidence-aware

The system SHALL persist the literal requester wording, one primary decision,
and competing intent hypotheses as versioned, immutable artifacts. Every material hypothesis MUST
record ambiguity, ownership, researchability, decision consequence, source
basis, disposition, and next action, and the artifact MUST retain exact parent
lineage and a deterministic content digest.

#### Scenario: Ambiguous business brief preserves competing interpretations

- **WHEN** a requester asks for the business model of an "app" without naming a payer or desired decision
- **THEN** the persisted frame SHALL retain the literal wording and at least two competing hypotheses, and SHALL NOT derive a technical stack scope from the topic word alone

#### Scenario: Enabler remains traceable to the primary decision

- **WHEN** a frame contains a technical enabler or constraint hypothesis
- **THEN** the hypothesis SHALL carry the exact primary-decision id and delivery consumers SHALL be able to reject an unbound stack claim

#### Scenario: Hypothesis omits ownership or consequence

- **WHEN** a caller submits a material hypothesis without a valid owner, researchability, decision consequence, disposition, or next action
- **THEN** validation SHALL fail before any ledger artifact or lifecycle revision is written

### Requirement: Clarification policy is bounded and deterministic

The system SHALL choose reconnaissance for agent-researchable ambiguity and
MUST return at most one open requester question for material requester-owned
ambiguity that cannot be safely ranked by available evidence. Replaying the
same frame SHALL produce the same action and question digest.

#### Scenario: Researchable uncertainty chooses reconnaissance

- **WHEN** unresolved alternatives are research-owned and have a bounded validation path
- **THEN** the policy SHALL return a reconnaissance action and SHALL NOT ask the requester a question

#### Scenario: Requester-exclusive material choice needs clarification

- **WHEN** unresolved alternatives change the primary decision, are requester-owned and non-researchable, and evidence cannot rank them
- **THEN** the policy SHALL return exactly one bounded open question with the competing hypothesis ids and a reason

#### Scenario: Multiple unresolved choices cannot produce multiple prompts

- **WHEN** more than one requester-exclusive ambiguity is present
- **THEN** policy evaluation SHALL select one deterministic question and record the remaining choices as deferred next actions

#### Scenario: Reconnaissance makes no progress

- **WHEN** a research-owned reconnaissance action returns no new evidence
- **THEN** the frame SHALL require a reframe or an explicit retained-consequence disposition before strategy readiness can be granted

### Requirement: DecisionFrame readiness gates strategy and autonomous work

The system SHALL persist a versioned `DecisionFrame` whose status is
`ready_for_strategy` only when every material ambiguity has an evidence-backed
selection or explicit requester disposition. StrategyProjection, ResearchPlan,
and autonomous dispatch SHALL require the exact current ready frame for the
same run and target; stale, unrelated, or legacy-only frames MUST fail closed.

#### Scenario: Unresolved material ambiguity blocks strategy

- **WHEN** a caller attempts strategy formation with a current frame containing a material unresolved requester choice
- **THEN** the coordinator SHALL reject the operation without changing lifecycle state or dispatching work

#### Scenario: Ready frame permits strategy-bound dispatch

- **WHEN** a current ready frame has exact run, target, hypothesis, and source lineage
- **THEN** the coordinator SHALL permit the downstream strategy/plan or dispatch operation and retain the frame reference in its event lineage

#### Scenario: Stale frame cannot authorize a new run

- **WHEN** a frame belongs to another run, is superseded, or is not the current frame revision
- **THEN** the coordinator SHALL reject it as stale without mutating canonical state

#### Scenario: Legacy or technical-substitution path cannot bypass the frame

- **WHEN** a legacy RunStore brief, Blueprint Target, or technical stack claim is supplied without the exact ready frame and primary-decision lineage
- **THEN** strategy, research-plan, handoff, and autonomous dispatch SHALL be rejected with no lifecycle mutation

### Requirement: DecisionFrame serialization is cross-host and replay safe

The system SHALL validate a versioned JSON schema and support deterministic
replay, idempotent identical persistence, conflict rejection for changed event
payloads, and atomic rollback when a frame write fails partway through.

#### Scenario: Identical frame replay is idempotent

- **WHEN** the same frame and event id are submitted twice
- **THEN** the second submission SHALL return the existing revision without duplicating artifacts or advancing the run twice

#### Scenario: Changed replay payload is rejected

- **WHEN** an existing frame/event id is reused with a different literal request or hypothesis digest
- **THEN** the coordinator SHALL raise a conflict and leave the prior ledger revision unchanged

#### Scenario: Fault during frame batch rolls back

- **WHEN** persistence fails after validation but before the frame and lifecycle event commit
- **THEN** neither the partial frame nor its state transition SHALL remain visible after reload

#### Scenario: Cross-host evaluator metrics use the same frame digest

- **WHEN** Codex, Claude Code, and Hermes serialize the same frame and run the black-box intent-substitution cases
- **THEN** intent-hypothesis fidelity, clarification appropriateness, premature-strategy rejection, primary-decision fidelity, decision-surface substitution, and enabler traceability SHALL be evaluated against one canonical digest
