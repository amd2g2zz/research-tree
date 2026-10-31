## ADDED Requirements

### Requirement: dependency-aware dispatch

#### Scenario: open dependency never dispatches
- **WHEN** a stage depends on a non-closed stage
- **THEN** it never appears in the dispatch set

#### Scenario: closing admits in the same pass
- **WHEN** the dependency completes
- **THEN** the dependent stage dispatches

#### Scenario: concurrency cap
- **WHEN** more stages are ready than maxConcurrency
- **THEN** at most maxConcurrency dispatch

### Requirement: task retry and stage park

#### Scenario: failed task re-dispatches
- **WHEN** failStage runs on an in-progress stage
- **THEN** the stage returns to pending with incremented retries and re-dispatches

#### Scenario: retries exhaust → park
- **WHEN** retries reach max_retries
- **THEN** the stage parks

#### Scenario: orphans park without blocking critical
- **WHEN** the orphan stage fails and the critical stage is in-progress
- **THEN** the orphan parks while the critical continues

### Requirement: isolated output paths

#### Scenario: no file conflicts
- **WHEN** multiple stages dispatch
- **THEN** each carries a unique output path
