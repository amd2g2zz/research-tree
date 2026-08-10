## Why

Alpha1 filesystem RunStore rounds contain useful historical lineage, but their
validation, closure, and delivery claims may have passed structural-only gates.
Alpha2 needs a repeatable migration path that preserves source history without
turning legacy strings into current canonical authority.

## What Changes

- Add an idempotent RunStore importer with a deterministic source fingerprint
  and durable import receipt.
- Copy valid legacy artifact and event lineage into SQLite as explicitly
  `legacy_unverified` historical records.
- Quarantine malformed sources and record run-id/source conflicts without
  mutating legacy files or existing canonical runs.
- Support dry-run inspection before a canonical import.

## Non-Goals

- Import alignment databases, native checkpoints, Hermes state, or remote
  content. Those remain separate migration slices.
- Revalidate legacy findings or permit legacy closure/completion claims to
  satisfy Alpha2 requirements.
