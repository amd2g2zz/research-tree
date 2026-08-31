## Context
The Alpha2 registry predates `lifecycle` and has no consumer, leaving packages, local installations, runtime, build, and evaluation material without one executable boundary.

## Goals / Non-Goals
- Keep one registry entry for every tracked or supported local root.
- Make schema, registry, and ignore validation read-only and deterministic.
- Keep generated packages, local copies, runtime, raw, and evaluation output distinct from authoring input; document collision-aware manual migration.

- Move, delete, stage, regenerate, install, or clean user paths.
- Add a package builder, alter runtime ownership, or automate a research run.

## Decisions

1. **Read the shipped schema without a new dependency.** Derive required fields, types, enums, and conditional migration requirements, then report sorted errors.

2. **Discover roots from Git and the checkout.** Compare `git ls-files` and the filesystem to the registry; exclude `.git` and report registered local material as protected.

3. **Use exact ignore rules.** Installed, runtime, build, cache, raw, and evaluation entries require explicit rules so broad patterns cannot hide drift.

4. **Keep package regeneration separate.** The checker verifies boundaries; the existing builder remains the acceptance oracle.

5. **Document, never automate, migration.** Require inspection, collision review, confirmation, and verification before a manual move.

## Risks / Trade-offs

- [Unknown roots or dirty checkout] -> stable diagnostics; protected paths stay untouched.
- [Schema or package drift] -> schema-derived validation or independent parity fails.

## Migration Plan

1. Add lifecycle/inventory entries and exact ignore rules, then run checker and package parity from a clean checkout.
2. Inspect existing operator data/collisions and obtain confirmation before a manual move; rollback only tracked registry, checker, ignore, and docs.
