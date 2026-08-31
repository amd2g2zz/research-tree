## ADDED Requirements

### Requirement: Parent acceptance binds merged closure-quality children

The system SHALL mark group 39 verified only when groups 46 and 47 are both
verified with complete source-bound receipts whose source revisions are
reachable from the parent integration revision. The parent SHALL record its
own exact acceptance command and rollback instruction, and SHALL not claim
runtime behavior beyond the two child contracts.

#### Scenario: Both child receipts are reachable

- **WHEN** groups 46 and 47 have verified receipts and both revisions are
  ancestors of the parent baseline
- **THEN** group 39 may record a parent acceptance receipt and #152 may close

#### Scenario: A child receipt is missing or stale

- **WHEN** either group 46 or group 47 is unverified, malformed, or not
  reachable from the parent baseline
- **THEN** parent acceptance fails and group 39 remains non-verified
