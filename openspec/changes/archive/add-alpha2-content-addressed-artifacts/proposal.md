## Why

The SQLite RunLedger records canonical lineage but must not hold large source
captures, binaries, images, or experiment output. Alpha2 needs immutable,
deduplicated bytes whose digest and availability can be resolved from ledger
metadata without making an unregistered blob evidence.

## What Changes

- Add a workspace-scoped SHA-256 content-addressed store beneath
  `.research-tree/cas/sha256/<prefix>/<digest>`.
- Stage and fsync bytes, verify digest and size, then publish immutably without
  replacing an existing object.
- Add SQLite content metadata and artifact binding tables, with idempotent
  registration and conflict rejection.
- Verify bytes on every read and quarantine unreferenced staged or published
  objects after interrupted registration.
- Keep legacy RunStore import, remote object storage, and evidence semantics out
  of this issue.

## Impact

This change extends the SQLite schema from version 1 to version 2 and adds the
`ContentAddressedStore` public API. Existing RunStore files and canonical
artifact JSON remain unchanged.
