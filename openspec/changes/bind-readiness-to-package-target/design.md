## Context

`CanonicalReadinessVerifier` resolves one Blueprint Target from the package,
then sends traced Findings and Decisions to strict evidence authorization. The
current helper only compares Finding and Decision payloads with each other.
Because low-level ledger append is intentionally generic, the package Target
must be an explicit trust boundary.

## Goals / Non-Goals

**Goals:**

- Pass the resolved package Target into strict authorization.
- Reject any strict Finding or selected/conditional Decision whose
  `blueprint_target_id` or exact Target parent reference is not that Target.
- Preserve the existing same-target Target/Slot, evidence, and option checks.

**Non-Goals:**

- Changing the ledger schema or canonical compilers.
- Implementing canonical DeliveryCompiler support (#110).

## Decisions

`_evaluate_package` already owns the authoritative `sources["target"]`, so it
will pass that `ArtifactRevision` to `_strict_findings_are_authoritative`.
The helper will derive the exact `ArtifactRef(round_id, id, revision)` for the
package Target. It will reject foreign Finding payloads or parent references
before building its evidence index, and reject foreign active Decision payloads
or parent references before checking parent closure. This keeps the check at
the public Readiness path instead of relying on callers to pre-validate ledger
writes.

An alternative was to reject foreign IDs in `_resolve_package_sources`; that
would validate only package references and would not protect a forged payload
or an artifact whose parent lineage points to another Target. The authorization
helper is the narrower, defense-in-depth boundary.

## Risks / Trade-offs

- [Risk] Historic malformed packages may fail strict readiness earlier.
  -> Mitigation: legacy Readiness remains unchanged; diagnostics identify the
  package Target mismatch.

## Migration Plan

No data migration. Deploy the check, rerun strict readiness for existing
packages, and repair any package whose traced graph is not rooted in its
canonical Target.
