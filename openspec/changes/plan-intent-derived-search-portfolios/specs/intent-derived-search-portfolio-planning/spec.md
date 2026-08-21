## ADDED Requirements

### Requirement: Planning derives bounded decision coverage

The runtime SHALL expose a pure intent-derived SearchPortfolio planner. Given
the exact intent, Working Brief, strategy, Decision Slot, and evidence-deficit
revisions, it SHALL create a strict SearchPortfolio and exactly one bounded
subquestion for mechanism, counterevidence, implementation, edge-case,
validation, and consequence coverage. Each planned subquestion SHALL record an
evidence class, expected decision effect, closure oracle, and stop/replan
trigger.

#### Scenario: A deficit lacks coverage keywords
- **WHEN** the supplied evidence deficit contains no coverage-category keyword
- **THEN** the planner still creates the bounded decision-relevant coverage set
  without depending on keyword detection

### Requirement: Rewrites retain exact planning lineage

Every query rewrite SHALL use a stable query reference only and bind the
intent, Working Brief, strategy, Decision Slot, and evidence-deficit revisions.
It SHALL not store raw query material, prompts, retrieval output, or execution
state.

#### Scenario: A planner output is inspected
- **WHEN** a caller inspects a rewrite
- **THEN** it can resolve every planning revision and its decision effect
  without reading raw query text

### Requirement: Human reopen is material-change only

The planner SHALL mark human-decision reopening only when the supplied change
dimensions include `authority`, `safety`, or `requester-outcome`. Evidence or
implementation-only changes SHALL remain autonomous replanning inputs.

#### Scenario: Evidence changes without authority expansion
- **WHEN** evidence and implementation dimensions change but authority, safety,
  and requester outcome do not
- **THEN** the planner does not reopen the human decision
