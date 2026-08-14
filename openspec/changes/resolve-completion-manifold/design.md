# Design

`RunLedger.list_completion_input_registrations()` returns every current,
non-quarantined typed registration grouped by role. The coordinator resolves
that set into a deterministic manifold instead of selecting the latest artifact
by kind. P0 closure registrations are keyed by slot and reject missing or
duplicate current slots; singleton roles reject zero or multiple registrations.

The delivery fields are validated as one lineage: the human report names and
parents the exact technical package, and the acceptance has exactly those two
parents, current revision tokens, the displayed pair digest, the shared
manifest digest, an accepted decision, and a human actor. Malformed references
become field diagnostics rather than uncaught parser errors.

`complete()` computes a canonical manifold digest and stores both the manifold
and digest in the immutable completion record. The record parents every
resolved input, including all closure slots. Repeated completion for the same
manifold is idempotent. A superseded or quarantined registration is excluded on
the next read, so `why_not_complete()` reports the affected field and a stale
completed run cannot be re-accepted silently.

The existing replay implementation continues to validate its established
state/event contract; the new digest is carried by the completion record rather
than duplicated into run-state replay fields.
