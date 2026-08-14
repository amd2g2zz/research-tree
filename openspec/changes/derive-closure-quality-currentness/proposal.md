## Why

`SlotClosureAssessor` currently persists caller-provided provenance groups,
counterevidence text, and contradiction booleans as if they were closure
facts. A shape-correct graph can therefore claim closure quality, and a token
can remain apparently valid after a bound evidence, adjudication, or OracleRun
revision is superseded.

## What Changes

- Derive provenance independence from the current evidence graph's provenance
  group, acquisition method, and provider identities.
- Require a current, independently reviewed closure adjudication for
  counterevidence and reviewer/method separation; derive contradiction status
  from Finding effects and adjudication references.
- Bind the closure token to canonical graph references and derived quality
  fields, with deterministic serialization independent of caller strings.
- Add `SlotClosureAssessor.is_current()` to recompute a passed token against
  the current ledger revisions.
- Register Alpha2 group 47 / GitHub issue #161 as a verified child of group 46.

## Non-Goals

This change does not implement correction invalidation, completion admission,
HostEvent ingestion, CLI routing, or group-39 aggregate acceptance.

## Impact

The change affects `research_tree.closure`, its package exports, focused closure
tests, and the Alpha2 OpenSpec execution, verification, issue, and delivery
registries.
