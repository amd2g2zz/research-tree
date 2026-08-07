## ADDED Requirements

### Requirement: Every confirmed Alpha1 baseline case is executable
A confirmed Alpha1 defect SHALL have a versioned fixture, pinned baseline commit,
actual host package path and digest, replay environment, documented command, and
semantic unsafe predicate. A catalogued but non-executable entry SHALL be marked
pending and SHALL NOT count as baseline reproduction coverage.

#### Scenario: Clean pinned checkout replays a case
- **WHEN** the evaluator runs a case from a clean repository checkout
- **THEN** it materializes the declared Alpha1 commit in a temporary isolated
  worktree
- **AND** records command, host package identity, fixture digests, exit code,
  stdout/stderr digests, and semantic result

### Requirement: Filler reports reproduce structural-only completion
The Alpha1 filler-report fixture SHALL contain only minimum headings and padding.
When supplied to the pinned Hermes adapter after a verified batch, a successful
`complete` status SHALL be recorded as `vulnerability_reproduced`.

#### Scenario: Padding report reaches complete
- **WHEN** a clean Alpha1 Hermes package processes the versioned filler reports
- **THEN** its completion command succeeds with `status` equal to `complete`
- **AND** the baseline receipt status is `vulnerability_reproduced`
- **AND** the receipt states that this is a legacy vulnerability reproduction,
  not a candidate fix confirmation

### Requirement: Baseline results do not masquerade as fix confirmation
A baseline runner SHALL NOT emit `fix_confirmed`. Future candidate evaluation
requires a case-bound, resolvable, independently reviewed execution receipt.

#### Scenario: Baseline run completes without candidate evidence
- **WHEN** a baseline case executes
- **THEN** its status is `vulnerability_reproduced` or `inconclusive`
- **AND** it is never reported as a confirmed fix

### Requirement: Forged validation is not evidence
The Alpha1 forged-validation fixture SHALL be executable against the pinned
Claude native adapter and SHALL independently prove that its declared evidence
reference does not resolve. A successful parser result with `status: passed`
SHALL be recorded as `vulnerability_reproduced`, never as fix confirmation.

#### Scenario: Native adapter accepts an unresolvable passed validation
- **WHEN** the clean Alpha1 checkout validates the versioned Finding Pack
- **AND** the harness resolves its `evidence_ref` under the isolated workspace
- **AND** no evidence artifact exists at that path
- **THEN** the historical command still exits zero and returns `validation_result.status` equal to `passed`
- **AND** the receipt records `evidence_resolves` equal to `false`
- **AND** the receipt contains command, environment, package, input, and output digests
- **AND** the receipt does not contain `fix_confirmed`

### Requirement: The adversarial corpus has one governed nine-defect manifest
The Alpha1 adversarial corpus SHALL publish one versioned manifest containing
exactly the nine issue #55 defect identifiers. Each entry SHALL declare either
`executable` with a fixture, harness, receipt, and semantic predicate, or
`pending` with an explicit reason and no reproduction claim. Pending entries
SHALL NOT count toward baseline coverage.

#### Scenario: Corpus coverage is machine-checkable
- **WHEN** the group-1 acceptance test loads the adversarial manifest
- **THEN** it finds exactly the nine named defect identifiers
- **AND** every executable entry resolves its fixture, harness, and redacted receipt
- **AND** every executable receipt has `status` equal to `vulnerability_reproduced`
- **AND** the manifest reports pending entries without treating them as reproduced
