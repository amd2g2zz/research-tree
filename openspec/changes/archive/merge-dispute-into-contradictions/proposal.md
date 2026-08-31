# Proposal: merge-dispute-into-contradictions

## Why

Issue #424 folds the dispute governance layer into the contradiction module.
The dependency direction is one-way (`dispute -> contradictions`; contradictions
never imported dispute), so the merge has a single clean direction. The two
KIND constants keep their wire values (`dispute-ledger`,
`provider-validation`), and the coordinator pressure-signal path keeps its
exact behavior: the production change is an import-source switch, not a
behavior change.

Four dispute entrypoints had zero consumers anywhere (production, scripts,
hooks, tests): `derive_dispute_from_contradiction`, `derive_with_disputes`,
`claim_ids_in`, and `record_provider_validation`. They retire with the merge
instead of being carried into the merged module as dead public API, and
negative tests lock their absence.

## What Changes

- `src/research_tree/dispute.py` is deleted. All retained symbols move
  verbatim into `src/research_tree/contradictions.py` in a marked section
  behind the existing classification code.
- `coordinator.py` switches the import source for the 11 dispute symbols to
  `from .contradictions import ...`; the `ingest_pressure_signal` method body
  is untouched (byte-identical behavior).
- The dedicated suite `tests/test_dispute_governance.py` renames to
  `tests/test_contradictions_dispute_governance.py` with every assertion kept
  and the import source switched to the merged module.

- Four dead dispute entrypoints retire: `derive_dispute_from_contradiction`,
  `derive_with_disputes`, `claim_ids_in`, and `record_provider_validation`.
  Negative tests lock their absence (module gone; symbols absent from the
  merged module and its `__all__`).
- KIND constants keep their wire values; persisted dispute-ledger artifacts
  (including stored `pressure_ledger` payloads) stay decodable by
  `dispute_packet_from_payload` without migration.

## Capabilities

### New Capabilities

- `dispute-governance-merge`: single-module surface for contradiction
  classification plus dispute governance: one import source, verbatim symbol
  bodies, zero coordinator behavior change, dead entrypoints locked out.

## Risk

Low. The dependency direction is one-way, consumers are two import sites
(coordinator plus the dedicated suite), and persisted artifacts keep their
KIND wire values and payload schema. The four retiring entrypoints have zero
callers (grep + call-graph verified); negative tests lock the retirement.
