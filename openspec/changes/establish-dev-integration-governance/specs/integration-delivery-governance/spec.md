## ADDED Requirements

### Requirement: Alpha2 has one protected development integration branch
The repository SHALL keep `master` as its default and release branch, SHALL use
`dev` as the integration branch for Alpha2 development, and SHALL require ordinary
Alpha2 implementation PRs to target `dev`.

#### Scenario: Feature PR targets dev
- **WHEN** an Alpha2 implementation PR is evaluated
- **THEN** its base branch is exactly `dev`
- **AND** a different base is rejected before merge

#### Scenario: Repository default remains master
- **WHEN** repository branch configuration is inspected
- **THEN** the default branch is `master`
- **AND** this default does not authorize Alpha2 feature PRs to target `master`

#### Scenario: Release promotion targets master
- **WHEN** a release promotion PR is evaluated
- **THEN** its head is a release branch derived from `dev`
- **AND** its base may be `master`
- **AND** ordinary feature changes in the same PR are rejected

#### Scenario: Bootstrap revision is auditable
- **WHEN** the `dev` integration branch is initialized
- **THEN** the exact source revision, validation commands, results, and branch
  protection state are recorded in a versioned bootstrap receipt

### Requirement: Development starts from a clean dedicated worktree
Every delivery issue SHALL have one dedicated branch and one dedicated worktree
created from the current `origin/dev` revision.

#### Scenario: Clean preflight succeeds
- **WHEN** the branch name contains the issue identifier, the worktree is unique,
  the base revision equals the fetched `origin/dev`, and `git status --porcelain`
  is empty
- **THEN** preflight emits a machine-readable receipt authorizing implementation

#### Scenario: Dirty worktree is rejected
- **WHEN** tracked, untracked, staged, conflicted, or unexpected generated files are
  present before implementation
- **THEN** preflight fails without stashing, deleting, resetting, or modifying them

#### Scenario: Stale base is rejected
- **WHEN** the recorded base revision differs from the current fetched `origin/dev`
- **THEN** preflight fails and requires the worktree to be recreated or rebased

### Requirement: One issue owns one active delivery surface
The governance check SHALL reject simultaneous active branches, worktrees, or PRs
that claim the same delivery issue, and SHALL reject one PR claiming multiple
implementation issues.

#### Scenario: Duplicate issue ownership is detected
- **WHEN** two active delivery branches, worktrees, or open PRs declare the same issue
- **THEN** the check reports every conflicting surface and fails

#### Scenario: Multi-issue delivery PR is detected
- **WHEN** an implementation PR claims to close or implement more than one issue
- **THEN** the PR gate fails and requires the work to be split

#### Scenario: Epic and release metadata do not masquerade as implementation
- **WHEN** an epic or release-tracking issue references several child issues
- **THEN** it is treated as governance metadata rather than a multi-issue
  implementation PR

### Requirement: Pull requests have bounded review size
The PR gate SHALL calculate changed files and non-generated line changes separately
from generated packages and SHALL enforce the configured review thresholds.

#### Scenario: Split review is required
- **WHEN** a PR exceeds 25 changed files or 800 non-generated changed lines
- **THEN** the gate requires a recorded split review and rationale

#### Scenario: Oversized PR is rejected
- **WHEN** a PR exceeds 50 changed files or 1500 non-generated changed lines without
  a maintainer-approved exception artifact
- **THEN** the gate fails

#### Scenario: Generated output is counted separately
- **WHEN** generated host packages change
- **THEN** their files and lines are reported separately
- **AND** they cannot hide an oversized source change

### Requirement: Generated packages are not authoring surfaces
Canonical source changes SHALL precede generated host-package updates, and package
parity SHALL be verified independently.

#### Scenario: Generated package changes without source fail
- **WHEN** a generated host package changes without its canonical source or builder
  input changing
- **THEN** the PR gate fails as generated drift

#### Scenario: Source and generated changes use separate commits
- **WHEN** a PR updates canonical skill source and generated packages
- **THEN** the generated package update is isolated in a distinct commit
- **AND** the package build check reproduces it exactly

### Requirement: Worktree cleanup is evidence-driven and non-destructive
The repository SHALL inventory every registered worktree before cleanup and SHALL
remove only worktrees whose disposition is proven safe.

#### Scenario: Dirty worktree is preserved
- **WHEN** a worktree contains tracked or untracked changes
- **THEN** cleanup classifies it as preserved and performs no destructive action

#### Scenario: Merged clean worktree is eligible
- **WHEN** a worktree is clean, its PR is merged into `dev`, its branch has no later
  commits, and its head is reachable from `origin/dev`
- **THEN** the inventory marks it eligible for explicit removal

#### Scenario: Orphaned historical work is not silently deleted
- **WHEN** a branch or worktree belongs to a closed-unmerged or stacked historical PR
- **THEN** cleanup requires a recorded preserve, replay, supersede, or discard
  disposition before removal
