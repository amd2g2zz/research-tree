## Claim model

`Claim` is an atomic scoped assertion. Its `ClaimGrounding` contains only an
exact canonical `EvidenceAnchor`; the evaluator resolves its bytes, selector,
scope/version/conditions metadata, and provenance itself. `ProvenanceCluster`
groups records by resolved upstream identity, owner, dataset/measurement
origin, or content fingerprint. A `ClaimAssessment` derives one admission
state from those records.

`candidate`, `isolated`, `rejected`, and `superseded` are audit-only and have
zero decision authority. Only `corroborated` can authorize a material search
batch to stop. `contested` remains reserved for #248.

## Search boundary

`assess_acquisition_batch` accepts validator-produced claim assessments. It
does not accept caller-selected admission or source quality as authority. A
material non-corroborated assessment forces `deepen` with a typed
cross-validation action. Existing raw outcome data remains diagnostic and does
not itself establish corroboration.

## Canonical decision boundary

Every strict Finding observation declares its claim identity. A supporting
option effect names the claims on which it relies. The canonical Decision
Ledger compiler re-resolves those Finding anchors and re-computes admission
before selected or conditional convergence; it does not trust a persisted
assessment or caller-owned strings. Thus delivery, readiness, and closure only
consume claim support after the canonical decision boundary has admitted it.
