## ADDED Requirements

### Requirement: Parent acceptance consumes reachable canonical Finding Pack receipts

The #171 parent acceptance SHALL depend on verified groups 79 and 80. Before
the parent receipt is accepted, each child command receipt's source revision
MUST be reachable from the parent baseline.

#### Scenario: Parent verifies child evidence

- **WHEN** the parent acceptance test inspects groups 79 and 80
- **THEN** both records are verified and each source revision is an ancestor of
  the parent `HEAD`

### Requirement: Parent acceptance remains metadata-only

The #171 parent evidence SHALL publish only its focused acceptance-test source
module and no public surface. It MUST NOT delete the retired compiler or add a
runtime adapter, bridge, fallback parser, alias, dual store, or exported
compatibility helper.

#### Scenario: Parent registers completion evidence

- **WHEN** the parent command runs after both child merges
- **THEN** it passes the child lineage checks and parent ownership test without
  changing a runtime implementation or child receipt
