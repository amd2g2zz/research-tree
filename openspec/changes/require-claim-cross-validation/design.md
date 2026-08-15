## Claim model

`Claim` is an atomic scoped assertion. Its `ClaimGrounding` binds an exact
source capture, extract range, original wording, and a validator-produced
entailment result. `ProvenanceCluster` groups records by a resolved upstream
identity, owner, dataset/measurement origin, or content fingerprint. A
`ClaimAssessment` derives one admission state from those records.

`candidate`, `isolated`, `rejected`, and `superseded` are audit-only and have
zero decision authority. Only `corroborated` can authorize a material search
batch to stop. `contested` remains reserved for #248.

## Search boundary

`assess_acquisition_batch` accepts validator-produced claim assessments. It
does not accept caller-selected admission or source quality as authority. A
material non-corroborated assessment forces `deepen` with a typed
cross-validation action. Existing raw outcome data remains diagnostic and does
not itself establish corroboration.

## Compatibility

Existing outcome schemas remain readable. Batches that do not declare a
material claim retain their ordinary acquisition behavior; consequential
callers must supply the admission assessment before using a stop result.
