## Design

`render-delivery` writes a deterministic Technical Research Package and Human
Research Report from `delivery-snapshot.json`. The snapshot records its source
run revision, task counts, validation outcomes, independent-review state, host
availability, and unresolved obligations. Its digest is embedded in both
reports.

`complete` regenerates the snapshot from the unchanged state and compares each
report byte-for-byte with the deterministic projection. It returns a
field-level metric mismatch when a known metric has changed. The adapter still
emits only `delivery_pending`; coordinator completion remains authoritative.
