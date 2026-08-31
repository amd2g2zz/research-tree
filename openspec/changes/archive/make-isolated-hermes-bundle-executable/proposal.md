## Why

The checked-in Hermes package lists its scripts as resources, but the staging
command only follows references written in `SKILL.md`.  As a result, a staged
GitHub bundle can validate as compatible even when its documented executable
entrypoints fail outside the source checkout because a transitive sibling module
was not copied.

## What Changes

- Define the executable closure for every Hermes script documented as a package
  entrypoint, including transitive local Python imports and the resources used
  by those entrypoints.
- Make package validation and `stage` reject an incomplete closure before they
  report `compatible=true` or publish a staged bundle.
- Cold-start every documented Hermes entrypoint from an unrelated working
  directory with no source checkout or ambient `PYTHONPATH`.
- Preserve reproducible generated-package parity and add an isolated
  provider-failure/recovery smoke path.

## Capabilities

### New Capabilities

- `isolated-hermes-executable-bundle`: Hermetic staged Hermes bundles whose
  documented Python entrypoints have validated dependency and resource closure.

### Modified Capabilities

None.

## Impact

This changes `scripts/build_skill_packages.py`,
`scripts/hermes_skill_adapter.py`, their generated Hermes package output, and
the Hermes/package regression suites.  It adds no third-party dependency and
does not change coordinator authority or native HostEvent semantics.
