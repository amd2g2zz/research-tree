## ADDED Requirements

### Requirement: reconnaissance emits independent methods
A canonical reconnaissance plan emits at least one MethodHypothesis per available method when the available set has ≥2 entries. Methods carry basis_refs and rationale; the planner does not collapse to a single ask_one path.

#### Scenario: ≥2 methods
- **WHEN** available_methods has ≥2 entries
- **THEN** propose_methods returns a plan with at least that many method hypotheses

#### Scenario: empty method set
- **WHEN** available_methods is empty
- **THEN** propose_methods raises ReconnaissanceError
