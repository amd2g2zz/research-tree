## ADDED Requirements

### Requirement: methods route by claim type with declared requirements

#### Scenario: literature claims
- **WHEN** a literature claim is verified
- **THEN** the receipt requirements include multi-source cross and verbatim anchors

#### Scenario: logic claims
- **WHEN** a logic claim is verified
- **THEN** the receipt requires fresh-context blind re-derivation

#### Scenario: market/judgment claims
- **WHEN** a market/judgment claim is verified
- **THEN** the receipt requires triangulation >= 3 independent sources

### Requirement: the counter-evidence quota is fail-closed

Every make-or-break claim gets >= 1 dedicated refutation-seeking round; convergence is blocked while unmet.

#### Scenario: quota unmet blocks convergence
- **WHEN** a make-or-break claim has 0 refutation rounds and assertConvergenceReady runs
- **THEN** it raises naming the quota

#### Scenario: the refutation round satisfies the quota
- **WHEN** a refuting verification follows the supporting one
- **THEN** assertConvergenceReady passes

### Requirement: single-source claims are never promoted to supported

#### Scenario: honest single-source marking
- **WHEN** a claim has 1 supporting source
- **THEN** the verdict is "supported-single-source", never plain "supported"

#### Scenario: two independent sources promote
- **WHEN** a claim has 2 supporting sources
- **THEN** the verdict promotes to "supported"

### Requirement: the search envelope is disclosed

#### Scenario: envelope present on every receipt
- **WHEN** a verification receipt is produced
- **THEN** it carries queried/not_queried/found/not_found

### Requirement: evidence is content-addressed

#### Scenario: non-sha256 refs rejected
- **WHEN** evidence_refs contain non-content-addressed values
- **THEN** verify raises
