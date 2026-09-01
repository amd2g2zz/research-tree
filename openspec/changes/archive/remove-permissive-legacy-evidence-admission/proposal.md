## Why

The evidence boundary still exposes compatibility forms that can describe an
artifact without an exact ledger reference, resolve it from an in-memory map,
or mark it `legacy_unverified`. Those forms are not authoritative evidence and
allow callers to bypass the canonical RunLedger admission contract.

## What Changes

- **BREAKING**: require `EvidenceArtifact.evidence_class` and a canonical
  status; remove `legacy_unverified` from the runtime and active v1 schema.
- **BREAKING**: require every `EvidenceAnchor` to contain an exact
  `ArtifactRef`; remove `allow_legacy`, no-reference serialization, and the
  `legacy_unverified` anchor payload.
- **BREAKING**: retain only ledger-backed `EvidenceResolver` construction;
  remove its artifact-map constructor and the unused public provenance helper.
- Keep `FindingPackCompiler` and the #165 reserved RunStore fixture. Its
  typed-evidence parser no longer admits a legacy anchor, while historic
  generic non-evidence observations remain outside this canonical admission
  slice.
- Register Alpha2 group 83 / issue #168 after verified group 82.

## Capabilities

### New Capabilities

- `strict-evidence-admission`: Admit evidence only through explicit,
  ledger-backed artifacts and anchors; reject every prior compatibility form.

## Impact

This is a deliberate public API cutover. Canonical callers retain
`EvidenceArtifact`, `EvidenceAnchor`, `EvidenceRepository`, and
`EvidenceResolver.from_ledger`. Legacy payloads, map-backed resolution, and
the unused provenance normalizer lose support without a bridge, alias,
fallback parser, migration, or dual state. Rollback is a Git revert.
