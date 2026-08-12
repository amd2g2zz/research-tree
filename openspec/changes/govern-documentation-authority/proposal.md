## Why

Documentation authority is currently implicit: a contributor can mistake a
generated package, historical RT specification, or operational receipt for the
current product contract. The existing registry is incomplete and has no
enforced checker, allowing terminology, links, generated copies, and document
placement to drift without a deterministic failure.

## What Changes

- Publish a complete, discoverable documentation authority index with canonical
  edit locations, owners, audiences, lifecycle, triggers, supersession, and
  validation rules.
- Add a deterministic documentation gate for registry coverage, lifecycle
  integrity, internal links, active terminology, generated package provenance,
  and report/session-log placement.
- Link contributor and user entry points to the authority model and align active
  delivery terminology with the Technical Research Package and Human Research
  Report contract.
- Preserve historical documentation as traceable, non-normative records rather
  than rewriting or deleting it.

## Capabilities

### New Capabilities

- `documentation-authority-governance`: Registry and executable drift gates for
  normative, generated, historical, operational, and evaluation documentation.

### Modified Capabilities

- None.

## Impact

Affected surfaces are the documentation authority registry, a new
`scripts/check_docs.py` command and focused tests, active contributor/user
documentation, and generated-package parity checks. Generated `packages/`
files remain build outputs and are never edited directly.
