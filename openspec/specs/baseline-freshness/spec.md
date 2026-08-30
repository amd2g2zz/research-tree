<!-- generated from openspec/changes/baseline-freshness-policy:PR #350 (#327) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: repository baselines carry freshness admission
Every repository baseline admission records inspected commit, authority commit, observation timestamp, ahead/behind divergence, relevant path changes, the policy in force, and a discrete disposition.

#### Scenario: stale relevant path
- **WHEN** divergence exceeds policy bounds AND changed paths overlap a relevant prefix
- **THEN** disposition is stale_relevant (consumers must revalidate, block-scope, or request explicit authorization)

#### Scenario: stale irrelevant path
- **WHEN** divergence exceeds policy bounds AND no relevant prefix matches
- **THEN** disposition is stale_irrelevant (baseline is recorded but does not block by itself)

#### Scenario: offline authority
- **WHEN** authority commit is None (remote unreachable)
- **THEN** disposition is freshness_unknown (never silently current; not a global block)

#### Scenario: historical analysis authorized
- **WHEN** policy.allow_historical_analysis is true and the caller passes historical_analysis_authorized=true
- **THEN** disposition is historical_analysis_authorized (divergence is recorded but the run proceeds under explicit acknowledgement)

#### Scenario: within bounds and no overlap
- **WHEN** ahead/behind within policy bounds AND no relevant path changes
- **THEN** disposition is current
