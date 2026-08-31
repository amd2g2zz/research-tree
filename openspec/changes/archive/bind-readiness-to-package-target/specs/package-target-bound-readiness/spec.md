## ADDED Requirements

### Requirement: Strict readiness is rooted in the package Blueprint Target

The strict Readiness path SHALL compare every traced strict Finding and every
selected or conditional Decision to the exact Blueprint Target resolved from
the Technical Package. Each applicable artifact SHALL both name that Target in
its payload and retain its exact `ArtifactRef` as a direct parent. A foreign
Target or foreign Target parent SHALL make both decision closure and
implementation readiness fail.

#### Scenario: A foreign Finding and Decision form an internally consistent graph

- **WHEN** a Technical Package names Target A but its strict Finding and
  selected Decision name Target B
- **THEN** strict Readiness SHALL reject the graph and SHALL NOT report passing
  decision closure or implementation readiness

#### Scenario: Canonical Target lineage is unchanged

- **WHEN** the package Target, strict Finding, and selected Decision all name
  the same persisted Target and retain valid evidence parents
- **THEN** strict Readiness SHALL preserve the existing evidence and semantic
  checks and may pass

#### Scenario: Payload forges the package Target while parent lineage is foreign

- **WHEN** a strict Finding or selected Decision names Target A in its payload
  but has Target B instead of the exact Target A revision in `parent_refs`
- **THEN** strict Readiness SHALL reject the forged graph and SHALL NOT report
  passing decision closure or implementation readiness
