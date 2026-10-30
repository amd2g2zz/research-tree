## ADDED Requirements

### Requirement: subagent dispatch rides the pi-subagents extension

rt-core maps the 4 worker classes onto custom agent types; the extension owns sessions and fleets.

#### Scenario: one agent type per worker class
- **WHEN** agent definitions are built
- **THEN** each of the four worker classes has a mapped custom agent type carrying its contract (verification = fresh-context blind)

### Requirement: dispatch carries the claim context

The dispatch prompt includes the stage's claims with state, posterior and premise links.

#### Scenario: the worker knows what it stands on
- **WHEN** a stage with claim c1 (standing on premise) dispatches
- **THEN** the prompt names c1 and the premise link

### Requirement: dispatch policy stays engine-side

Concurrency comes from the scheduler's ready-set cut; the adapter dispatches only stages the scheduler marked.

#### Scenario: unmarked stages do not dispatch
- **WHEN** a stage has no assigned worker class
- **THEN** dispatch returns empty (the scheduler decides who runs)
