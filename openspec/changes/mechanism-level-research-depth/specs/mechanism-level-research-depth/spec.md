## ADDED Requirements

### Requirement: promoted sources carry a mechanism artifact

The batch assessment SHALL accept `mechanism_records` describing promoted
sources. A mechanism record SHALL carry a non-empty `approach` (what the
approach is), a non-empty `how_it_works` (how it works), and parallel
`evidence_refs`/`evidence_kinds` where at least one evidence kind is beyond
the README (`code-inspected`, `design-doc`, or `experiment`). A record whose
evidence kinds are all `readme` SHALL be rejected by the contract. When a
batch whose disposition would be `stop` (submit for closure) covers captured
sources that lack a mechanism record, the assessment SHALL be forced to
`deepen` with the next action `require-source-mechanism`, and SHALL name the
uncovered refs in `missing_mechanism_refs`.

#### Scenario: promotion without a mechanism artifact fails

- **WHEN** a fully-covered batch with captured sources is assessed and no
  mechanism record covers those sources
- **THEN** the disposition is `deepen` with next action
  `require-source-mechanism` and `missing_mechanism_refs` names every
  uncovered captured source

#### Scenario: a README-only mechanism record is rejected

- **WHEN** a mechanism record declares only `readme` evidence kinds
- **THEN** constructing or decoding the record raises a contract error and
  the promotion gate cannot be satisfied with it

#### Scenario: a complete mechanism record lets a covered batch submit for closure

- **WHEN** every captured source of a promotable batch is covered by a valid
  mechanism record with beyond-README evidence
- **THEN** the assessment keeps the `stop` disposition and
  `missing_mechanism_refs` is empty

### Requirement: cross-comparison clusters captures by mechanism

The batch cross-comparison SHALL accept an optional `mechanism_summary` on
each capture record. Captures whose normalized mechanism summaries are
equivalent SHALL collapse into one mechanism cluster regardless of upstream
identity, the comparison SHALL report `distinct_implementations` as the
mechanism cluster count, and provenance-distinct captures whose mechanism is
equivalent to an earlier capture SHALL be tagged in `mechanism_duplicates`
against the cluster's first capture. Captures that are already provenance
duplicates SHALL NOT be re-tagged as mechanism duplicates. Captures without a
declared mechanism summary SHALL be reported in
`undeclared_mechanism_capture_refs`, and a mechanism-duplicate capture SHALL
NOT count as a new unique identity for its outcome's measured novelty.

#### Scenario: N same-mechanism different-URL projects do not count as N distinct implementations

- **WHEN** two captures with different upstream identities declare equivalent
  mechanism summaries
- **THEN** they land in one mechanism cluster, the second capture is tagged a
  mechanism duplicate against the first, `distinct_implementations` is 1, and
  the second capture's outcome novelty is not `new`

#### Scenario: different mechanisms stay distinct

- **WHEN** two provenance-distinct captures declare different mechanism
  summaries
- **THEN** they land in two mechanism clusters, no mechanism duplicate is
  tagged, and `distinct_implementations` is 2

#### Scenario: captures without a mechanism summary are reported undeclared

- **WHEN** a capture declares no mechanism summary
- **THEN** it appears in `undeclared_mechanism_capture_refs`, is not part of
  any mechanism cluster, and does not inflate the distinct-implementation
  count

### Requirement: shallow source depth blocks landscape-slot closure

The recursive search SHALL record per-source engagement declared on Finding
Pack payloads (`sources` with `ref` and `depth`) and valid `mechanism` records
on the slot. For a slot whose oracle requires landscape coverage (default;
`landscape_required: false` opts out), a source whose deepest declared
engagement is `none`/`snippet`/`summary` depth SHALL raise a named closure
blocker, and a source engaged at `full-source`/`experiment` depth without a
valid mechanism record SHALL raise a mechanism closure blocker; in both cases
the slot SHALL NOT be a closure candidate and the engine SHALL schedule a
mandatory deeper follow-up action on the same source. Drilling the source to
full-source/experiment depth with a valid mechanism record SHALL clear both
blockers.

#### Scenario: shallow depth blocks landscape-slot closure and schedules a deeper batch

- **WHEN** a Finding Pack declares a source at `snippet` depth for a
  landscape slot and the evidence batch is applied
- **THEN** the stop evaluation reports a shallow-depth closure blocker for
  the slot, the slot is not a closure candidate, and a mandatory follow-up
  action naming the source is on the frontier

#### Scenario: a full-source source without a mechanism artifact blocks closure

- **WHEN** a Finding Pack declares a source at `full-source` depth with a
  mechanism record that fails the beyond-README requirement
- **THEN** the stop evaluation reports a mechanism closure blocker for the
  source and the drill-down follow-up remains scheduled

#### Scenario: drilling the source clears the blockers

- **WHEN** a later Finding Pack declares the same source at
  `full-source`/`experiment` depth with a valid mechanism record
- **THEN** no shallow or mechanism blocker remains for that source and the
  slot may become a closure candidate again when its other oracles pass
