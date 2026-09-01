# Delta: strategy-handoff

## ADDED Requirements

### Requirement: Post-confirm revise_strategy supersedes with an invalidation marker

Once an authoritative confirmed projection exists, `revise_strategy` SHALL
NOT write a `displayed` revision. The coordinator SHALL append a
`strategy-projection-invalidation` marker artifact (schema 1: id, run_id,
superseded_projection_ref, superseded_display_digest,
superseded_authority_fingerprint, reason) parented to the superseded
projection, then append the revision as a `draft` whose parent lineage
includes the marker. `latest_confirmed` SHALL return no authoritative
confirmation until a successor revision passes the full display gate and is
re-confirmed.

#### Scenario: Post-confirm revision is draft with a marker, never displayed

- **WHEN** `revise_strategy` runs on a run whose confirmed projection exists
- **THEN** the revision is persisted with status `draft`, a
  `strategy-projection-invalidation` marker names the superseded projection
  reference, display digest, and authority fingerprint, the marker reference
  appears in the revision's parent lineage, and `latest_confirmed` returns
  no confirmation

#### Scenario: Rejected revision leaves no marker behind

- **WHEN** the revised content fails projection validation
- **THEN** no invalidation marker is appended (the revision content is
  validated before any ledger write)

#### Scenario: Replayed confirmation against a superseded draft names the violated rule

- **WHEN** the `handoff_confirmed` transition guard is invoked with a
  confirmation payload whose recorded authority fingerprint does not match a
  superseded draft revision
- **THEN** the guard rejects with `authority_fingerprint_drift` (content
  checks run before the displayed-status check), and a guard pass additionally
  requires displayed/confirmed status
