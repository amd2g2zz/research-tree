## Context

The umbrella Alpha2 change contains an initial registry, but it covers only a
subset of the repository and no tracked checker enforces its metadata. #62 has
renamed the active delivery terminology to Technical Research Package and Human
Research Report, while historical RT records must retain their original terms.

## Goals / Non-Goals

**Goals:**

- Make one JSON registry the canonical index for governed documentation roots.
- Validate registry schema, lifecycle/supersession integrity, canonical sources,
  internal Markdown links, active legacy terminology, generated package parity,
  and invalid report/session-log paths.
- Make the model discoverable from README and contributor workflow guidance.

**Non-Goals:**

- Rewrite all historical content or alter generated package files directly.
- Govern user-owned runtime data, report contents, or release readiness.

## Decisions

- Use a declarative JSON registry in the umbrella change because it is already
  the declared delivery-matrix source and has a stable authority location.
- Treat registry entries as root prefixes. The checker finds tracked Markdown
  documentation and requires each to belong to exactly one most-specific root,
  avoiding a brittle manually maintained per-file inventory.
- Permit retired terminology only for `historical` and `superseded` entries, or
  an explicit `legacy_compatibility` annotation. Active entries fail with a
  path and line number.
- Prove generated documentation through the existing package build `--check`
  command, invoked by the checker rather than duplicated generation logic.
- Emit deterministic structured JSON errors so tests and CI can identify the
  exact violated rule.

## Risks / Trade-offs

- [New Markdown roots are not registered] → fail closed for tracked docs while
  exempting non-document source and generated/runtime roots.
- [Package build adds validation cost] → only run it when generated package
  coverage is declared in the registry.
- [Legacy terminology is widespread] → scope the ban to explicitly active
  roots and keep historical roots traceable.

## Migration Plan

Add registry metadata and checker first, repair only active entry documents,
then use `scripts/check_docs.py` in CI. Rollback reverts tracked registry,
checker, test, and discoverability changes; it does not remove historical or
user-owned material.
