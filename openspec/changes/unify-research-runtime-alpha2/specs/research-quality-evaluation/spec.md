## ADDED Requirements

### Requirement: Evaluation uses versioned real-task and adversarial cases
The system SHALL maintain replayable cases covering vague intent, incorrect human assumptions, incorrect agent assumptions, infeasible goals, repository-backed research, conflicting sources, multimodal inputs, recursive discovery, unavailable tools, provider failure, crash recovery, and material post-handoff feedback.

#### Scenario: Case contains hidden eventual implementation material
- **WHEN** a test case is prepared from a historical repository outcome
- **THEN** the worker receives only time-appropriate public inputs and the evaluator retains the hidden oracle outside the request

### Requirement: Quality metrics measure semantic outcomes
The evaluation SHALL measure intent fidelity, premature handoff, unsupported claims, P0 coverage, contradiction handling, oracle reproducibility, false completion, implementation rediscovery burden, independent implementation success, recovery, host parity, and human acceptance.

#### Scenario: Report contains many URLs and headings but unsupported decisions
- **WHEN** structural proxy counts are high while consequential claims lack valid evidence
- **THEN** the evaluation records semantic failure rather than increased research depth

### Requirement: Independent oracles and experts calibrate automated checks
The system SHALL use deterministic invariants first and SHALL supplement them with hidden fact or implementation oracles, isolated implementation runners, and blinded expert review; an uncalibrated LLM judge SHALL NOT be the sole release authority.

#### Scenario: Automated rubric approves a shallow package
- **WHEN** an independent implementation runner must rediscover consequential decisions or cannot identify the first implementation slice
- **THEN** the package fails implementation usefulness regardless of the automated prose score

### Requirement: Alpha2 has non-negotiable false-completion gates
The release process SHALL reject alpha2 if any adversarial case falsely completes, any P0 closure or report claim has an unresolved reference, provider/crash recovery loses obligations, or semantically equivalent hosts violate the parity contract.

#### Scenario: One host bypasses closure after worker completion
- **WHEN** Codex, Claude Code, or Hermes reaches complete without the required core closure artifacts
- **THEN** the alpha2 release gate fails for all hosts until the bypass is corrected

### Requirement: Evaluation compares alpha2 with explicit baselines
The system SHALL compare exact alpha2 artifact revisions against alpha1 and a simpler prompt-based baseline using the same public case inputs and evaluator-owned oracles.

#### Scenario: Alpha2 adds process without improving outcomes
- **WHEN** alpha2 does not improve independent implementation, factual discipline, intent fidelity, or recovery over the registered baselines
- **THEN** the evaluation reports the regression or lack of benefit and does not infer success from added workflow

### Requirement: Evaluation evidence is preserved for audit
The system SHALL persist case version, source permission, baseline revision, environment digest, public materials, commands, raw artifacts, evaluator results, limitations, and component diagnoses.

#### Scenario: Release result is challenged
- **WHEN** a reviewer requests evidence for an alpha2 quality claim
- **THEN** the exact case, run artifacts, oracle result, comparison, and known limitations are retrievable without rerunning the agent

### Requirement: Each quality metric has a frozen measurement definition

The evaluation manifest SHALL define numerator, denominator, unit, aggregation, unavailable-data handling, and evidence path for intent_fidelity, premature_handoff, unsupported_claim, false_completion, p0_closure, recovery_loss, host_parity, implementation_success, rediscovery_burden, and human_acceptance.

#### Scenario: A dimension is not applicable

- **WHEN** a case cannot exercise implementation or recovery
- **THEN** the evaluator records not_applicable with a reason and excludes it from the denominator

#### Scenario: A claim is unsupported

- **WHEN** a consequential report claim has no resolvable Evidence Anchor or OracleRun
- **THEN** unsupported_claim increments and the case cannot pass its semantic gate

### Requirement: Evaluation runners and expert review have explicit interfaces

The public case manifest SHALL expose only permitted inputs. The hidden fact/implementation oracle, independent runner, and blinded expert reviewer SHALL have versioned request and result schemas, commands, environment identities, and limitation fields.

#### Scenario: Hidden material leaks into a request

- **WHEN** a request contains a reference patch, discussion, hidden test body, or oracle answer
- **THEN** request construction fails before the worker is launched

#### Scenario: Reviewers disagree

- **WHEN** blinded reviewers produce materially different rubric outcomes
- **THEN** the evaluator records both scores, agreement status, adjudication, and whether the release threshold is still met

### Requirement: Causal attribution requires a controlled comparison
The evaluation system SHALL classify a behavior seen in one transcript as an
observation, not a model-, host-, provider-, or skill-specific cause. A causal
attribution SHALL require registered comparison runs that hold the brief,
Context Pack, skill revision, available tools, authority, environment, and
success oracle constant while varying only the declared factor.

#### Scenario: One Claude Code and GLM5.2 transcript fails
- **WHEN** one retained transcript shows premature handoff, stale-plan continuation, or shallow research
- **THEN** the result records the behavior as observed and the cause as unresolved until a controlled comparison provides discriminating evidence

#### Scenario: Comparison runtime is unavailable
- **WHEN** the registered comparison model or host cannot be executed
- **THEN** the comparison is marked unavailable with a named blocker and cannot count as passing parity or causal-attribution evidence

#### Scenario: Multiple factors change between runs
- **WHEN** a comparison changes the model and also changes the skill revision, tools, context, or oracle
- **THEN** the evaluator rejects causal attribution and records the run only as non-controlled supporting context

### Requirement: The reported Claude Code and GLM5.2 failure is a release fixture
The evaluation corpus SHALL include a redacted, versioned fixture derived from
the reported conversation, including activation ordering, compound questioning,
correction invalidation, task-identity isolation, recursive research depth,
claim provenance, and dual-delivery expectations.

#### Scenario: Candidate repeats the historical failure chain
- **WHEN** the candidate reads supporting references before activation, asks a compound alignment question, continues a corrected stale plan, changes the research subject, or completes after one unverified worker round
- **THEN** the fixture fails and identifies the earliest violated state transition and its dependent consequences

#### Scenario: Candidate corrects the historical behavior
- **WHEN** the candidate preserves task identity, transactionally applies corrections, performs evidence-bearing recursive research, and satisfies both delivery oracles
- **THEN** the fixture records the exact trace, artifacts, and reviewer evidence without claiming that an untested model or host caused the baseline failure

### Requirement: Search depth and continuity are evaluated as outcomes

The evaluation SHALL include cases where a first search batch is relevant but shallow, where implicit mechanisms are absent from the initial wording, where one provider returns repeated secondary sources, where a source is captured before a crash, and where evidence invalidates the initial strategy. Metrics SHALL include implicit-subquestion coverage, independent-method coverage, deepening correctness, pivot correctness, source-capture retention, checkpoint-resume success, and rediscovery burden.

#### Scenario: Multiple queries use one provider

- **WHEN** the candidate issues many rewritten queries through one provider
- **THEN** the evaluator counts provider-boundary diversity as one and does not award multi-method coverage for query volume

#### Scenario: Candidate stops after a shallow first wave

- **WHEN** primary evidence, implementation detail, or validation remains open
- **THEN** the case records premature research stop even if the candidate produced a polished report

### Requirement: Adversarial and validation gates are tested as execution behavior

The evaluation SHALL inject anchored but fabricated claims, landscape-only completion attempts, missing OracleRuns, self-review attempts, and adversarial negative results. It SHALL reject a candidate that preserves the claim, prepares delivery, or reports a closed Slot without the required independent adversarial and validation outcomes.

#### Scenario: Fabricated claim carries a syntactically valid URL anchor

- **WHEN** a worker submits a claim with an unreachable, mismatched, or unresolvable anchor
- **THEN** the evaluator records unsupported_claim and the run cannot pass a consequential evidence gate
