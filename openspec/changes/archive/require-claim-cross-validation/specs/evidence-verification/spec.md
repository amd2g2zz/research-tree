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

### Requirement: Non-admitted claims cannot converge a canonical decision

The canonical Decision Ledger compiler SHALL re-resolve the EvidenceAnchors
and re-compute claim admission for every claim used by a supporting effect of a
selected or conditional option. It SHALL reject the decision when any such
claim is not `corroborated`. Persisted admission state and worker-provided
capture, extract, source, or provenance strings SHALL NOT authorize the
decision.

#### Scenario: Forged strict Finding has one source

- **WHEN** a caller manually appends a strict-looking Finding Pack whose
  supporting effect names a claim grounded by only one canonical source
- **THEN** selected or conditional decision convergence rejects that Finding
  Pack rather than allowing delivery, readiness, or closure to consume it
