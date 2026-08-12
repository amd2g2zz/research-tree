## ADDED Requirements

### Requirement: Lifecycle transitions enforce the strategy macro-stage boundary
The coordinator SHALL map detailed states to four requester-visible stages and SHALL reject every path from alignment or handoff_pending to stage-3 research unless the current displayed StrategyProjection digest has explicit contextual confirmation.

#### Scenario: Direct dispatch bypass is attempted
- **WHEN** a host, worker, hook, legacy run store, task list, or report path requests research dispatch without current projection confirmation
- **THEN** the coordinator rejects the request and preserves the current lifecycle and macro-stage digest

#### Scenario: Internal research loop returns to autonomous work
- **WHEN** synthesis or readiness identifies a researchable deficit under the confirmed strategy
- **THEN** the detailed state may return to autonomous_research while the requester-visible macro stage remains stage 3

