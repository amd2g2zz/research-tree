# Design

`RunLedger.append_completion_input_batch()` validates and commits a complete
typed batch under one SQLite transaction. The batch records each immutable
artifact, exact parent rows, a dedicated completion registration, a lineage
event, and the resulting run revision. A matching complete retry returns the
existing revisions; a partial or conflicting retry is rejected.

`CompletionInputRegistrar.write_delivery_pair()` is the only canonical
delivery writer. It requires the canonical technical and human kinds, binds
the human payload and parent list to the next technical revision, and uses the
fixed `canonical-delivery-compiler-v1` issuer. `write_delivery_acceptance()`
requires current canonical pair revisions, exact `artifact_id@revision`
tokens, a matching displayed-pair digest, a deterministic manifest digest,
human actor, and both pair refs as parents. Its issuer is fixed to
`human-delivery-acceptance-v1`.

When a delivery payload supplies a shared manifest, both surfaces must contain
the same canonical manifest and its digest is registered. Existing compiler
payloads without a manifest use an immutable digest of the two exact refs and
content hashes; this adds no rendering or document-shape change.

Correction quarantine and stale replacement are enforced by the ledger's
current-parent checks. Generic `append_artifact()` never writes a registration,
and direct registration attempts with a replacement issuer are rejected for
the delivery and acceptance roles.
