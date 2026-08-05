## ADDED Requirements

### Requirement: Alignment preserves both human and agent beliefs
The system SHALL persist human statements, agent interpretations, supporting basis, confidence, disagreement, supersession, and decision consequence as separate revisioned alignment records rather than overwriting them into one brief.

#### Scenario: Human feedback corrects an agent interpretation
- **WHEN** the user explains that an agent interpretation does not represent the intended outcome
- **THEN** the system appends the feedback and a superseding interpretation while retaining the prior interpretation and its basis

#### Scenario: Evidence challenges a human premise
- **WHEN** reconnaissance finds credible evidence that materially conflicts with a user premise
- **THEN** the system records both positions and their bases as a material disagreement instead of silently accepting either one

### Requirement: Alignment actions are selected from persisted decision state
The system SHALL choose among reconnaissance, one open question, constructive disagreement, and confirmation using the unresolved impact, human exclusivity, researchability, expected ambiguity reduction, decision consequence, cognitive load, and repetition history.

#### Scenario: Agent-verifiable ambiguity exists
- **WHEN** a high-impact uncertainty can be reduced through repository or external reconnaissance
- **THEN** the system records and executes a reconnaissance attempt before asking the user to supply the missing technical fact

#### Scenario: Human authority is required
- **WHEN** a consequential preference or permission cannot be inferred or researched by the agent
- **THEN** the system asks one open-ended question that explains the current understanding and decision consequence

### Requirement: User-facing alignment remains cognitively bounded
The system SHALL present a short mirror of current understanding, at most one relevant fact or counterargument, its consequence, and no more than one open prompt in a user-facing alignment turn.

#### Scenario: Multiple internal gaps remain
- **WHEN** the alignment graph contains several unresolved nodes
- **THEN** the system selects one highest-consequence prompt and retains the other gaps internally for later turns

### Requirement: Alignment attempts are durable and consumable once
The system SHALL assign every reconnaissance, question, disagreement, and confirmation candidate a persisted attempt identity and SHALL NOT issue another planning decision for the same pending attempt until an outcome is recorded or recovery marks it unknown.

#### Scenario: Planner is called repeatedly without an outcome
- **WHEN** the planner is invoked multiple times while a reconnaissance attempt is pending
- **THEN** it returns the same pending attempt or a waiting state rather than creating unlimited zero-turn reconnaissance

### Requirement: Autonomous handoff requires semantic readiness and contextual confirmation
The system SHALL permit handoff only when outcome, intended use, scope, delivery, authority, success oracle, feasibility, strategy, and material disagreements are sufficiently resolved, and the user explicitly confirms the displayed strategy digest.

#### Scenario: Generic acknowledgement follows a strategy draft
- **WHEN** the user replies only with a generic acknowledgement such as "okay" or "continue"
- **THEN** the system remains confirmation-pending and does not grant autonomous authority

#### Scenario: Alignment changes after display
- **WHEN** the alignment state changes after the strategy digest was shown
- **THEN** confirmation of the stale digest is rejected and a new strategy projection is required

### Requirement: Alignment readiness has a decidable predicate

Handoff readiness SHALL require non-empty, revisioned values for outcome, intended use, scope, non-goals, delivery contract, authority boundary, safety boundary, success oracle, feasibility assessment, strategy, and every P0 disagreement disposition. The predicate SHALL report each field as pass, fail, or unknown; "sufficiently resolved" without field-level results is invalid.

#### Scenario: One hard field is unknown

- **WHEN** the feasibility, authority, safety, or success-oracle check is unknown
- **THEN** the readiness predicate fails, identifies the field, and selects reconnaissance, one open question, or authority blocking

#### Scenario: An impossible request is discovered

- **WHEN** evidence shows that a requested outcome cannot be achieved under confirmed resources or permissions
- **THEN** the predicate enters authority_blocked with alternatives and a human decision request instead of creating a nominal research tree

### Requirement: Confirmation is bound to a canonical message envelope

Every user-facing alignment turn SHALL persist a message id, run id, displayed belief digest, selected action id, one prompt or no prompt, evidence refs, consequence, created time, and response binding. Only an explicit response that names or semantically accepts the displayed strategy digest can confirm handoff.

#### Scenario: User sends a repeated response

- **WHEN** the same response id is delivered twice
- **THEN** the second response is idempotently acknowledged and cannot create another confirmation or question attempt

#### Scenario: User says only "continue"

- **WHEN** the response does not accept the objective, scope, delivery, authority, and success fields
- **THEN** the run remains handoff_pending and the planner emits at most one next open prompt

### Requirement: Material post-handoff feedback creates traceable replanning
The system SHALL handle normal research corrections autonomously, but SHALL create a successor round when user feedback changes the target, priority, authority, or success definition.

#### Scenario: User changes the required outcome during autonomous research
- **WHEN** feedback materially changes the confirmed success definition
- **THEN** the active round is superseded with explicit lineage and the new round re-enters alignment

### Requirement: Corrections transactionally invalidate dependent state
The system SHALL treat a material requester correction as a typed FeedbackEvent
that identifies the contradicted belief or field, preserves the prior revision,
creates a successor interpretation, and marks every dependent pending action,
strategy digest, handoff, closure, readiness, delivery, and acceptance artifact
stale before another question, dispatch, or completion decision is allowed.
The event records `contradicted_refs`, `affected_fields`, `invalidated_refs`,
`successor_refs`, `impact_class`, and `task_identity_disposition`; task identity
marked `rederived` also carries the successor identity. Terminal feedback has a
terminal impact by default rather than being treated as informational.

#### Scenario: Correction invalidates a pending handoff
- **WHEN** the requester corrects the outcome or scope after a strategy digest is displayed
- **THEN** the correction and successor interpretation commit atomically, the displayed digest becomes stale, and confirmation or dispatch from that digest is rejected

#### Scenario: Diagnostic subject is mistaken for the research target
- **WHEN** the requester states that a repository or product discussed as evidence is not the subject of the current research
- **THEN** the task identity is re-derived from the current Context Pack and dependent domain-specific strategy state is superseded before planning resumes

#### Scenario: Correction arrives during an active research attempt
- **WHEN** a correction invalidates a premise used by a running or submitted attempt
- **THEN** the attempt is retained as historical evidence, its result cannot satisfy current closure, and the coordinator records cancellation, quarantine, or successor work according to the correction impact

### Requirement: Alignment responses bind to the pending action
The system SHALL accept a requester response only for the current pending
alignment action or as an explicitly typed unsolicited FeedbackEvent. A generic
record operation SHALL NOT resolve an arbitrary node or human-only field.

#### Scenario: Response names no pending action
- **WHEN** a response-recording command targets a node other than the current pending action and is not a typed FeedbackEvent
- **THEN** the command fails without changing readiness, turn state, or node status

#### Scenario: Agent-authored support targets a human-only field
- **WHEN** agent evidence or an agent interpretation is marked supported for a preference, permission, or acceptance field reserved to the requester
- **THEN** the field remains unresolved and handoff readiness reports the missing requester decision
