## ADDED Requirements

### Requirement: host attempts must normalize before canonical ingestion
Process exit is not completion truth. Every host attempt outcome carries process exit, timeout, provider disposition, usage disposition, expected and observed deliverables, and host/session/attempt identity before it may influence canonical state.

#### Scenario: exit zero with semantic failure
- **WHEN** an attempt records exit 0 with an authentication error, exhausted usage, or missing mandatory deliverables
- **THEN** it is classified to the semantic failure disposition and cannot become worker_finished, verified, or completed

#### Scenario: timeout before retry
- **WHEN** an attempt timed out or has no recorded exit
- **THEN** classification is unknown_outcome, which any retry must observe first

#### Scenario: dispositions are mutually exclusive
- **WHEN** several failure signals co-occur
- **THEN** documented precedence (timeout > auth > unavailable > incompatible > deliverables) yields exactly one disposition

#### Scenario: doctor separates installation from provider readiness
- **WHEN** doctor reports health
- **THEN** static installation health and live provider readiness are separate sections; unprobed provider state is unknown and no credentials or raw gateway logs appear
