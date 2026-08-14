## ADDED Requirements

### Requirement: A verified receipt digest matches its raw output

The active verification registry SHALL copy the receipt's output digest exactly,
and that digest SHALL equal the SHA-256 of the referenced raw output bytes.

#### Scenario: Historical group-60 receipt is internally consistent

- **WHEN** the group-60 verification test loads its receipt and raw output
- **THEN** the registry digest, receipt digest, and raw-output SHA-256 are equal
  and the focused acceptance suite passes
