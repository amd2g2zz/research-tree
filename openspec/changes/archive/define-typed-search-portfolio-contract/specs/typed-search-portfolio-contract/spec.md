## ADDED Requirements

### Requirement: Search portfolios are strict typed values

The runtime SHALL expose immutable `SearchPortfolio`, `Subquestion`,
`MethodSelection`, `RejectedMethod`, and `ReassessmentPolicy` values. A
portfolio SHALL contain exact schema identity, stable portfolio/run/slot and
intent/brief revision identifiers, unique subquestions, at least one selected
method, explicit rejected-method entries, a reassessment policy, and a valid
lifecycle status. Decoding SHALL reject unknown fields, malformed identifiers,
duplicate entries, unsupported enum values, and non-object JSON payloads. The
strict public payload SHALL use `search-portfolio-v2.json`; the historical
planning schema and fixture SHALL be removed rather than retained through a
legacy reader, alias, or migration path.

#### Scenario: Malformed portfolio payload is supplied
- **WHEN** a caller decodes a payload with an unknown field, duplicate ID, or
  unsupported status
- **THEN** the runtime rejects it with a typed portfolio validation error and
  does not construct a partial portfolio

### Requirement: Method registry proves selected boundaries

The runtime SHALL expose immutable `MethodRegistration` and `MethodRegistry`
values. Each registration SHALL bind exactly one method/provider pair to a
capability, failure boundary, availability state, and applicable degradation
reason. A selected method SHALL resolve to exactly one registration with an
equal failure boundary and SHALL be rejected when the registration is unknown
or unavailable. A rejected method SHALL resolve to a known registration and
record a controlled rejection reason.

#### Scenario: An unavailable method is selected
- **WHEN** a SearchPortfolio is validated against a MethodRegistry whose
  matching registration is unavailable
- **THEN** validation fails closed and no validated portfolio is returned

### Requirement: Independence is a method and provider boundary

The runtime SHALL expose deterministic method/provider boundary inspection for
a SearchPortfolio. Multiple query references on one selected method/provider
pair SHALL count as one boundary. An independence check for two or more
boundaries SHALL succeed only when the selected set contains the requested
number of distinct method IDs and distinct provider IDs.

#### Scenario: One provider receives several queries
- **WHEN** a portfolio contains multiple query references through one provider
- **THEN** those references cannot satisfy a two-boundary independence check

### Requirement: Portfolio serialization excludes raw query material

The typed portfolio JSON schema and `to_dict()` result SHALL contain only
identifier-shaped query references and controlled method reason values. The
runtime SHALL serialize subquestions, method selections, rejections, and
reassessment dispositions in canonical order so equivalent typed portfolios
produce identical JSON-compatible payloads.

#### Scenario: A stable typed portfolio is serialized
- **WHEN** a validated portfolio is serialized more than once
- **THEN** each result is identical and contains no raw query or private prompt
  field

### Requirement: Group 48 remains an independent contract slice

Alpha2 group 48 SHALL register the typed SearchPortfolio and MethodRegistry
contract as planned for GitHub issue #163. It SHALL depend only on the merged
foundation groups needed for evidence, policy, alignment, ratification, and
durable capture, and SHALL not change parent issue #83's group 27 ownership.

#### Scenario: Governance is inspected before parent integration
- **WHEN** the Alpha2 task, verification, issue, delivery, and umbrella
  registries are validated
- **THEN** group 48 is planned and mapped to #163 while group 27 remains
  unchanged
