## ADDED Requirements

### Requirement: the open-loop condition rolls stages up mechanically

已决 ∥ EVSI 饱和 ∥ 预算尽 → ROLLUP; otherwise drill-down.

#### Scenario: all claims decided
- **WHEN** every claim in the stage is decided
- **THEN** the decision is rollup with reason all-decided

#### Scenario: EVSI saturated
- **WHEN** every claim's EVSI/cost score is below the saturation threshold
- **THEN** the decision is rollup with reason evsi-saturated

#### Scenario: budget exhausted
- **WHEN** the stage budget is exhausted
- **THEN** the decision is rollup with reason budget-exhausted

### Requirement: belief propagation reopens descendants append-only

A refuted premise marks descendant claims stale (reopened, counted) — never deleted.

#### Scenario: refuted premise propagates
- **WHEN** a premise is refuted
- **THEN** all transitive descendants become stale with incremented reopen counters; unrelated claims are untouched

### Requirement: the 12h hard cap forces convergence with PARK fallback

#### Scenario: cap hit
- **WHEN** elapsed time reaches the global cap
- **THEN** forced convergence with PARK fallback is signaled

### Requirement: dispatch is dependency-aware with bounded concurrency and retry→park

#### Scenario: open dependency never dispatches
- **WHEN** a stage depends on a stage that is not rolled up
- **THEN** it never appears in the dispatchable set

#### Scenario: closing the dependency admits the stage
- **WHEN** the dependency rolls up
- **THEN** the dependent stage is dispatchable in the same pass

#### Scenario: concurrency cap and worker assignment
- **WHEN** more stages are ready than the concurrency limit
- **THEN** at most 4 dispatch with worker classes assigned round-robin

#### Scenario: retries exhausted park the stage
- **WHEN** a stage has exhausted its retries
- **THEN** it parks (never blocks the critical path)
