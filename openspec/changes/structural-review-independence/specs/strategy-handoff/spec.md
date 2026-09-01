# Delta: strategy-handoff

## ADDED Requirements

### Requirement: Post-confirm revise_strategy supersedes with an invalidation marker

Once a projection id carries confirmation history, `revise_strategy` SHALL
NOT write a `displayed` revision. The coordinator SHALL append the revision as
a `draft` first (a draft without its marker is fail-closed: the prior
authority stays the latest valid display and the draft cannot display without
the full gate), then append a `strategy-projection-invalidation` marker
artifact (schema 1: id, run_id, superseded_projection_ref,
superseded_display_digest, superseded_authority_fingerprint, reason)
parented to the superseded revision. Post-confirm branch selection SHALL key
on the projection id's confirmation history — a `handoff_confirmed` event has
ever named it — not on the `latest_confirmed` snapshot, which is permanently
void after the first supersede. The marker is invalidation evidence in the
run record; it has no dedicated diagnostics reader in this change.

#### Scenario: Post-confirm revision is draft with a marker, never displayed

- **WHEN** `revise_strategy` runs on a run whose projection id carries
  confirmation history
- **THEN** the revision is persisted with status `draft` before the marker is
  appended, a `strategy-projection-invalidation` marker names the superseded
  revision's reference, display digest, and authority fingerprint, and
  `latest_confirmed` returns no confirmation

#### Scenario: Every later post-confirm revision stays draft

- **WHEN** `revise_strategy` runs again after the first supersede voided
  `latest_confirmed`
- **THEN** confirmation history still selects the supersede branch, the new
  revision is persisted as `draft`, and a second marker names the superseded
  draft

#### Scenario: Rejected revision leaves no marker behind

- **WHEN** the revised content fails projection validation
- **THEN** no invalidation marker is appended (the revision content is
  validated before any ledger write, and the draft is appended before the
  marker)

#### Scenario: Replayed confirmation against a superseded draft names the violated rule

- **WHEN** the `handoff_confirmed` transition guard is invoked with a
  confirmation payload whose recorded authority fingerprint does not match a
  superseded draft revision
- **THEN** the guard rejects with `authority_fingerprint_drift` (content
  checks run before the displayed-status check), and a guard pass additionally
  requires displayed/confirmed status

### Requirement: A superseding draft can reach re-confirmation through the gate

The lifecycle matrix SHALL provide a human actor edge from
`autonomous_research` back to `alignment` (`alignment_feedback`), so the
superseding draft is re-displayable through the normal flow — a fresh
`alignment-verification` bound to the draft's authority fingerprint, the
displayed promotion, and the full #462 display gate — and can reach
re-confirmation instead of permanently blocking `delivery_accepted`.

#### Scenario: Legitimate fix-up reaches re-confirmation

- **WHEN** the human returns a post-supersede run to `alignment` via
  `alignment_feedback`, a fresh independent verification bound to the
  superseding draft's fingerprint is registered, the draft is promoted to a
  displayed revision, and the human confirms
- **THEN** the run advances through `alignment_projection_ready` and
  `handoff_confirmed`, and `latest_confirmed` names the promoted revision
