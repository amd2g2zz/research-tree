## Decisions

### Digest-addressed immutable files

The SHA-256 digest is both the identity and the integrity oracle. The locator
is derived from the digest and resolved only below the workspace root. A staged
file is written with `fsync`; publication uses a hard link so a concurrent
publisher cannot replace an existing object.

### Metadata and binding are separate from bytes

`content_objects` records digest, media type, byte size, locator, availability,
and creation time. `artifact_contents` binds one exact artifact revision to one
registered digest. A byte object is not canonical evidence until its metadata
is registered and its binding exists.

### Partial failure and recovery

CAS publication and SQLite commit cannot share one transaction. The durable
boundary is therefore explicit: bytes are staged and verified first, metadata
is registered second, and unreferenced staging or published objects are moved
to quarantine. Quarantine entries never resolve as canonical content.

### Idempotency

Ingesting equal bytes returns the same digest and does not create a second CAS
object. Registering identical metadata is a no-op; different metadata for the
same digest is a conflict. Binding the same digest to the same revision is a
no-op; rebinding to another digest is rejected.

## Rejected Alternatives

- SQLite BLOB columns: rejected because large writes increase lock duration and
  database churn.
- Mutable path-based references: rejected because replacement can silently
  change evidence after a claim was recorded.
- Delete-on-failure cleanup: rejected because recovery needs an auditable
  quarantine for interrupted publication.
