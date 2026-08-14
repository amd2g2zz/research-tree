## ADDED Requirements

### Requirement: Public RunStore scheduler surface is absent

The project SHALL not publish `AdaptivePortfolioScheduler`, `PortfolioError`,
`InvalidPortfolioError`, `WORK_PORTFOLIO_KIND`, or
`validate_portfolio_payload` from the root package. It SHALL not provide an
alias, facade, bridge, adapter, replacement scheduler, migration, fallback, or
user-data operation for retired `work-portfolio` state.

#### Scenario: A caller inspects the root package

- **WHEN** a caller inspects `research_tree` for retired scheduler symbols
- **THEN** none of those symbols resolves and no user-owned runtime data is
  accessed or changed

### Requirement: Active authority does not advertise a public scheduler

The active Alpha2 registries, requirements, task records, and current operational documentation SHALL not advertise the retired RunStore scheduler, its
`work-portfolio` persistence boundary, or `tests/test_scheduler.py`. Historical
`docs/specs/RT-010.md` and archived OpenSpec material MAY retain factual audit
history only.

#### Scenario: Active sources are inspected after retirement

- **WHEN** maintainers inspect current package exports and active authority
  artifacts
- **THEN** no public or current contract resolves the scheduler boundary

### Requirement: Scheduler source deletion remains separately owned

The project SHALL leave `src/research_tree/scheduler.py` physically present but
unreachable after this slice and SHALL not promote it as a supported private API
or add a runtime caller while awaiting the #179 source purge.

#### Scenario: The transition slice completes

- **WHEN** issue #178 is applied before #179
- **THEN** the module has no root export, current runtime caller, active
  contract, or dedicated behavior test
