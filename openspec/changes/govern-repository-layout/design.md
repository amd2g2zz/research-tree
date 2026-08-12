## Context
The Alpha2 registry predates its required `lifecycle` field and has no
consumer, leaving packages, local installations, runtime, build, and evaluation
material without one executable boundary.

## Goals / Non-Goals

**Goals:**

- Keep one registry entry for every tracked or supported local root.
- Make schema, registry, and ignore validation read-only and deterministic.
- Keep generated packages, local copies, runtime, raw, and evaluation output
  distinct from authoring input; document collision-aware manual migration.

**Non-Goals:**

- Move, delete, stage, regenerate, install, or clean user paths.
- Add a package builder, alter runtime ownership, or automate a research run.

## Decisions

1. **Read the shipped schema without a new dependency.** The checker derives
   required fields, types, enums, and conditional migration requirements from
   it, then reports sorted stable errors.

2. **Discover roots from Git and the checkout.** `git ls-files` and the
   filesystem are compared to the registry; `.git` is excluded and registered
   untracked material is reported as protected.

3. **Use exact ignore rules.** Installed, runtime, build, cache, raw, and
   evaluation entries require an explicit rule so broad patterns cannot hide
   source or package drift.

4. **Keep package regeneration separate.** The checker verifies boundaries;
   the existing builder remains the reproducibility oracle in acceptance.

5. **Document, never automate, migration.** The workflow requires inspection,
   collision review, confirmation, and verification before a manual move.

## Risks / Trade-offs

- [Unregistered root] -> stable diagnostic; no mutation.
- [Dirty checkout] -> registered local paths are protected; unknown paths fail.
- [Schema drift] -> schema-derived validation and focused parity test fail.
- [Package drift] -> independent package parity remains required.

## Migration Plan

1. Add lifecycle and full root inventory entries before enabling the checker.
2. Add only exact ignore rules for supported untracked roots.
3. Run the checker and package parity from a clean checkout.
4. Inspect existing operator data and collisions, then obtain explicit
   confirmation before any manual move.
5. Roll back only tracked registry, checker, ignore, and documentation changes.
