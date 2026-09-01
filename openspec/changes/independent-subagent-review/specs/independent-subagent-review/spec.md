## ADDED Requirements

### Requirement: Alignment display gate requires an independent verification

The coordinator SHALL reject `research-tree strategy display` and every
caller of the `alignment_projection_ready` transition with the named error
`independent_verification_required` unless the run holds a current
`alignment-verification` completion-input artifact whose
`authority_fingerprint` equals the projection's, whose `projection_ref`
resolves to a strategy-projection artifact of the displayed projection id in
the same run, whose `verifier_identity` and `session_context` are both
present and distinct, and whose independent restatement covers every success
oracle of the projection. An artifact that lacks either identity is never
independent and fails closed.

#### Scenario: Display without an alignment verification is rejected

- **WHEN** a falsifiable projection is displayed and the run holds no
  current `alignment-verification` artifact
- **THEN** the coordinator rejects with `independent_verification_required`,
  the run state is unchanged, and no lifecycle event is appended

#### Scenario: Same-identity verification cannot satisfy the display gate

- **WHEN** an `alignment-verification` artifact carries a
  `verifier_identity` equal to its `session_context` (self-review)
- **THEN** the display gate rejects with `independent_verification_required`

#### Scenario: Identity-free verification fails closed

- **WHEN** an `alignment-verification` artifact carries a blank or missing
  `verifier_identity` or `session_context`
- **THEN** the display gate rejects with `independent_verification_required`

#### Scenario: Independent verification lets the display proceed

- **WHEN** a current alignment verification with a distinct verifier
  identity, matching authority fingerprint, and a restatement of every
  projection oracle is registered before display
- **THEN** `research-tree strategy display` commits the displayed revision
  and the verification artifact's parent lineage includes the exact
  projection revision the verifier read

### Requirement: Delivery gate requires an independent delivery review

The coordinator completion manifold SHALL carry an
`independent_delivery_review` diagnostic that blocks `delivery_accepted`
unless the run holds exactly one current `delivery-review` completion-input
artifact whose `verifier_identity` and `session_context` are present and
distinct, whose `evidence_custody` references equal its parent lineage and
still resolve to current, non-quarantined artifacts of the run, whose
`per_oracle` verdicts cover every confirmed projection oracle, and whose
overall `verdict` is not `unmet`. The diagnostic SHALL fail with
`independent_review_required`, `verifier_not_independent`,
`evidence_custody_lineage`, `evidence_custody_stale`, `oracle_uncovered`, or
`independent_review_unmet`, and `why_not_complete` SHALL name
`resolve:independent_delivery_review` and per-oracle resolve entries. On
pass the completion record SHALL bind the review reference in
`independent_review_refs`.

#### Scenario: Delivery without a delivery review is blocked

- **WHEN** every other completion obligation is satisfied but the run holds
  no current `delivery-review` artifact
- **THEN** the diagnostic fails with `independent_review_required`,
  `why_not_complete` names `resolve:independent_delivery_review`, and
  `delivery_accepted` raises `CompletionBlockedError`

#### Scenario: Same-identity delivery review is blocked

- **WHEN** the only `delivery-review` artifact carries a
  `verifier_identity` equal to its `session_context`
- **THEN** the diagnostic fails with `verifier_not_independent` and
  `delivery_accepted` is blocked

#### Scenario: Uncovered oracle and unmet independent verdict block delivery

- **WHEN** the delivery review omits a confirmed projection oracle or
  records an overall `unmet` verdict
- **THEN** the diagnostic fails with `oracle_uncovered` naming the oracle
  or with `independent_review_unmet`, and `why_not_complete` names
  `resolve:independent_delivery_review:<oracle_id>` in the uncovered case

#### Scenario: Stale evidence custody reopens the review

- **WHEN** a custody reference of the delivery review no longer resolves to
  the current revision of that artifact
- **THEN** the diagnostic fails with `evidence_custody_stale` and delivery
  remains blocked

#### Scenario: Independent review completes and binds its reference

- **WHEN** an independent delivery review covers every oracle with a
  satisfied verdict over current custody references
- **THEN** `delivery_accepted` completes the run and the completion record's
  manifold carries `independent_review_refs` with the review reference

### Requirement: The independent gates are conjunctive with the existing gates

The alignment display gate SHALL run beside the #441 falsifiability review,
and the delivery review gate SHALL run beside the #443 goal_satisfaction
diagnostic, without replacing or weakening either: a projection rejected by
the falsifiability review stays rejected when an independent verification is
present, and a run whose goal satisfaction fails stays blocked when an
independent delivery review is present.

#### Scenario: Falsifiability failure blocks despite an independent verification

- **WHEN** a projection without evidence-standard-bound oracles is displayed
  and a current independent alignment verification exists
- **THEN** the display is still rejected, naming the falsifiability rule

#### Scenario: Goal satisfaction failure blocks despite an independent review

- **WHEN** a success oracle's goal_satisfaction verdict is `unmet` and a
  current independent delivery review exists
- **THEN** `delivery_accepted` is still blocked naming `goal_satisfaction`

### Requirement: Host guidance dispatches independent subagents before display and delivery

The behavioral layer SHALL instruct the agent, before
`research-tree strategy display`, to dispatch a fresh-context subagent that
reads only the original conversation and the projection draft and produces
an independent restatement of outcome, scope, authority, and each success
oracle, and, before delivery acceptance, to dispatch a fresh-context
subagent that reads only the Finding Packs and the confirmed oracles and
produces a per-oracle verdict with references to the packs it read. The
SKILL template, the Hermes skill template, and all three host adapters
SHALL carry that instruction, and each SHALL state that self-issued reviews
are rejected by the runtime gates.

#### Scenario: Skill templates and adapters carry the dispatch instruction

- **WHEN** the behavioral documents are inspected for the subagent dispatch
  instruction
- **THEN** SKILL.template.md and hermes-SKILL.template.md each contain the
  display and delivery dispatch guidance with the named rejection codes,
  and claude-adapter.md, codex-adapter.md, and hermes-adapter.md each name
  a fresh host-native subagent — never the agent's own session — before
  display and before delivery acceptance
