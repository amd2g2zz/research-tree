## ADDED Requirements

### Requirement: Consequential claims are grounded and independently admitted

The runtime SHALL represent every consequential external assertion as an atomic
scoped claim with exact source capture/extract references, original wording,
and validator-produced grounding. It SHALL derive provenance clusters from
upstream identity and origin metadata. Worker confidence, provider diversity,
method diversity, and URL count SHALL NOT establish corroboration. Only a
faithfully grounded claim supported by two independent provenance clusters may
receive the `corroborated` admission state.

#### Scenario: Two APIs return one upstream publication

- **WHEN** two claim groundings identify the same upstream publication through
  different providers or methods
- **THEN** they resolve to one provenance cluster and the claim remains
  `isolated`

#### Scenario: Independent grounded sources agree

- **WHEN** two faithful groundings for a scoped claim resolve to separate
  provenance clusters
- **THEN** the evaluator admits the claim as `corroborated`

### Requirement: Non-admitted material claims cannot stop acquisition

The Search Portfolio evaluator SHALL treat material `candidate`, `isolated`,
`rejected`, and `superseded` claims as zero-authority evidence. It SHALL emit
a cross-validation/deepen action instead of `stop` until all material claims
are corroborated.

#### Scenario: High-confidence isolated source

- **WHEN** a complete full-source acquisition batch includes a material
  isolated claim with declared high source quality
- **THEN** the batch disposition is `deepen`, not `stop`, and its next action
  requests independent cross-validation

#### Scenario: Non-entailing extract

- **WHEN** a selected extract does not entail the normalized claim within its
  version, time, scope, or conditions
- **THEN** the evaluator rejects the claim and the claim cannot authorize a
  stop disposition
