# Tasks: integrate-search-portfolio-lineage

## Implementation

- [x] 1. Add canonical `SearchPortfolioService` plan, registry, batch,
  assessment, decision, and validation boundaries.
- [x] 2. Bind acquisition dispatch and worker-finish HostEvents to current
  portfolio/query/method/assessment lineage.
- [x] 3. Feed typed assessment projections into the pure adaptive policy and
  enforce source/checkpoint latest-attempt validation.

## Verification

- [x] 4. Add red/green tests for complete lineage, current capture/checkpoint,
  acquisition dispatch, assessment-gated worker finish, and policy input.
- [ ] 5. Run the exact group-76 acceptance command and record a source-bound
  receipt after the implementation commit.
