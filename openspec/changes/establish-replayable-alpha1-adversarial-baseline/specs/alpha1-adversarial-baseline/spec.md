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
