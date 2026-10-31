## ADDED Requirements

### Requirement: the canvas is a pure projection of the ledger

#### Scenario: claims derive from the event stream
- **WHEN** a claim.upsert event lands
- **THEN** the canvas render shows the claim with posterior and tier

#### Scenario: deterministic
- **WHEN** two projections render from the same event stream
- **THEN** their views are identical

### Requirement: writes happen only through the five gates

pause-resume / kill-stage / park / verdict-confirm / append-info — anything else is structurally impossible.

#### Scenario: park requires revival conditions
- **WHEN** the park gate is called without revival conditions
- **THEN** it raises (PARK 必须带复活条件)

#### Scenario: verdict on the closed vocabulary
- **WHEN** verdict-confirm receives "MAYBE"
- **THEN** it raises naming the closed vocabulary

#### Scenario: append-info accepts context
- **WHEN** append-info carries a non-empty note
- **THEN** the gate accepts and the action is audited

#### Scenario: gates emit audited actions
- **WHEN** any gate accepts
- **THEN** a provider.action event lands in the stream (provider: canvas)
