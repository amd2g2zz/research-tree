## ADDED Requirements

### Requirement: mid-research user-update traces are verifiable

The registry carries `digest-first` (point, decision_relevance,
source_pointer) and `viewpoint-hints` (alternatives) trace types; turns that
must compose a user-facing update can be gated on them by name.

#### Scenario: a digest-first turn verifies
- **WHEN** a recorded turn carries a digest-first trace with all three fields
- **THEN** verify_traces satisfies `digest-first`

#### Scenario: viewpoint hints without alternatives fail
- **WHEN** a viewpoint-hints trace carries no alternatives
- **THEN** verification fails closed naming the field

### Requirement: Finding Packs carry a validated transformation record

When a Finding Pack declares a transformation record, ingestion validates it
as exactly `{ratio}` with a numeric value in [0, 1] and persists it.

#### Scenario: numeric ratio round-trips
- **WHEN** a pack is compiled with `transformation={"ratio": 0.75}`
- **THEN** the persisted payload carries `{"ratio": 0.75}`

#### Scenario: non-numeric ratio is rejected
- **WHEN** a pack declares `transformation={"ratio": "high"}`
- **THEN** ingestion raises an error naming the ratio requirement
