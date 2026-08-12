## ADDED Requirements

### Requirement: Preference observations are project-local, inspectable, and privacy bounded
The runtime SHALL persist only normalized project-scoped `PreferenceObservation` records with stable source lineage, explicit/inferred basis, privacy classification, reversal condition, and content digest, and MUST reject raw transcript, secret, psychological, demographic, or cross-project identity fields.

#### Scenario: Sensitive observation is submitted
- **WHEN** an observation uses a blocked privacy classification or sensitive inference key
- **THEN** validation fails and neither the observation nor profile state is persisted

### Requirement: Current explicit preference has immediate precedence
The runtime SHALL apply a current explicit preference immediately, supersede the prior active value with exact previous/next lineage, and MUST NOT allow an existing profile or inferred observation to override the current explicit requester intent.

#### Scenario: Current request contradicts the profile
- **WHEN** a current explicit observation conflicts with an active profile entry
- **THEN** the explicit value becomes active immediately and the prior value is retained as superseded with its reversal condition

### Requirement: Inferred preferences refresh with bounded hysteresis
The runtime SHALL refresh inferred evidence only at each five-observed-turn boundary, advance an entry by at most one status step per refresh, preserve an active value when a one-off inference contradicts it, and represent unresolved contradiction as contested active state plus a shadow alternative.

#### Scenario: One inferred contradiction arrives
- **WHEN** one inferred observation contradicts an active preference before or at a refresh boundary
- **THEN** it cannot reverse the active value and the exact alternative remains pending or shadowed for inspection

#### Scenario: Repeated consistent evidence refreshes
- **WHEN** consistent inferred observations span successive five-turn refresh boundaries
- **THEN** the entry advances no more than one hysteresis state per refresh and every transition cites its source observations

### Requirement: Preference profiles age without silent reversal
The runtime SHALL mark an unreinforced active preference stale after the configured refresh age while retaining its value and lineage, and SHALL require explicit input or repeated successor evidence before a different value becomes active.

#### Scenario: Active preference receives no reinforcement
- **WHEN** its last supporting observation exceeds the stale refresh threshold
- **THEN** the entry becomes stale without silently selecting another value

### Requirement: Project preference state survives reload and is administrable
The workspace SQLite ledger SHALL restore the exact latest profile revision and pending observations after reload and SHALL provide project-scoped inspect, correct, reset, and delete operations. Reset SHALL append an empty profile while retaining immutable observations read-only; delete SHALL remove only that project's preference records.

#### Scenario: Process reload occurs before refresh
- **WHEN** pending observations exist and the service is recreated from the same workspace
- **THEN** inspection returns the exact profile revision, next refresh boundary, and pending observation ids

#### Scenario: Project profile is reset or deleted
- **WHEN** reset is requested and later deletion is explicitly requested for one project
- **THEN** reset preserves immutable observation history, while deletion removes only that project's observations and profiles without exposing sensitive fields

### Requirement: Material preference influence is traceable
Every StrategyProjection materially affected by a project profile SHALL record the source profile revision, observation id, selected key/value, precedence, and reversal condition in its content-bound payload. A conflicting current explicit request SHALL take precedence and SHALL be recorded as such or cause profile influence to be omitted.

#### Scenario: Profile changes a strategy choice
- **WHEN** an active profile entry materially selects depth, delivery, method, or autonomy detail
- **THEN** the StrategyProjection digest binds a complete influence record that identifies how the choice can be reversed
