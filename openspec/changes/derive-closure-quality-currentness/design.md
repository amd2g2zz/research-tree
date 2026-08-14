## Context

Group 46 established the durable content and complete-Finding boundary. Group
47 consumes that boundary and makes quality a property of the exact current
graph rather than of assessor arguments. Existing `assess()` arguments remain
accepted for compatibility, but they are not authoritative inputs.

## Derived Graph

For every current strict Finding observation, the assessor resolves the exact
EvidenceArtifact, AcquisitionReceipt, SourceCapture, and origin chain. It
records the source provenance group, acquisition method, provider, and worker
identity. Independence requires at least two distinct provenance groups,
methods, and providers. A `closure-adjudication` artifact must be directly
bound to the target and complete Finding set and must identify a reviewer and
review method distinct from the producing workers and evidence methods.

Finding option effects derive contradiction references. A searched-without-
result adjudication satisfies counterevidence only when its reviewer and method
are independently bound. Contradictory findings remain active until a current
adjudication explicitly covers and resolves them. Caller strings and booleans
can conservatively block a pass but cannot create one.

## Token And Currentness

The token digest uses canonical JSON containing the target, decision, complete
Finding, evidence, adjudication, and OracleRun references plus derived checks,
provenance signatures, contradiction disposition, oracle verdicts, fallback,
and reversal condition. Assessment identifiers and caller quality strings are
excluded from token material. `is_current()` requires the persisted assessment
and every parent to be the latest revision, then recomputes the same material;
any superseded or unresolvable dependency returns `False`.

## Rollback

Revoke quality-derived tokens and retain immutable assessments as inconclusive
history. Group 46's durable evidence admission remains in force.
