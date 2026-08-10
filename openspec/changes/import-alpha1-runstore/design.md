## Import Boundary

The importer reads a complete `RunStore` round and computes a digest from every
regular source file path, size, and SHA-256 value. The source tree is never
modified. A `legacy_imports` SQLite receipt records digest, locator, target run,
disposition, detail, and timestamp.

## Trust Disposition

Each copied artifact has a `legacy-` kind and an immutable payload containing
the original artifact plus `legacy_disposition: legacy_unverified`. Imported
events are also named `legacy-*`. This preserves provenance while preventing a
legacy validation or completion string from being interpreted as Alpha2 closure.

## Failure Handling

Malformed source data is read-only quarantined with a receipt before any target
run is created. An existing target run with another source digest is a conflict,
not a merge. Replaying the same source digest returns `already_imported` and
does not append artifacts or events.
