## Context

The canonical runtime already writes evidence through `EvidenceRepository` and
resolves it through `EvidenceResolver.from_ledger`. The retained compatibility
forms are a separate admission path: a missing `ArtifactRef` is represented by
`legacy_unverified`, and `EvidenceResolver` can resolve an arbitrary caller
map. Those forms cannot establish durable evidence lineage.

## Goals / Non-Goals

**Goals:**

- Make exact RunLedger lineage mandatory for every typed evidence anchor.
- Require explicit evidence classification and canonical artifact status.
- Preserve canonical selector, content-integrity, locator, and metadata
  validation after removing map mode.
- Keep the existing RunStore compiler and #165 fixture without allowing its
  typed parser to decode a legacy evidence anchor.

**Non-Goals:**

- Deleting or replacing `FindingPackCompiler`, `RunStore`, or the #165
  assurance fixture.
- Adding a compatibility reader, adapter, alias, migration, fallback, or dual
  evidence store.
- Rewriting historical governed OpenSpec records that document prior formats.
- Claiming causal replay validates evidence; replay is outside this admission
  slice.

## Decisions

### Typed anchors always carry an ArtifactRef

`EvidenceAnchor` has a required `ArtifactRef` and serializes only the canonical
anchor object. `from_dict` accepts that exact shape and has no compatibility
keyword. This makes the typed anchor's identity independently resolvable before
it can become canonical Finding, decision, delivery, or readiness input.

### Resolution is ledger-only

The resolver requires a `RunLedger`, obtains the exact revision and bound
content from it, and applies all selector metadata checks in that strict mode.
The old artifact map was not a durable authority and is removed rather than
wrapped.

### Retain the compiler boundary but close typed admission

`FindingPackCompiler` remains for #165's separate retirement work. Its shared
typed-anchor normalization calls the strict parser, so a
`legacy_unverified` anchor cannot be compiled into a Finding Pack through that
path. The compiler's historical generic observations are not canonical typed
evidence and are neither extended nor migrated here.

### Preserve historical audit material

Prior OpenSpec changes may truthfully describe old formats. They are historical
evidence, not current runtime authority. The active Alpha2 schema, task
registry, public exports, and tests define the current contract.

## Risks / Trade-offs

- Consumers using positional map resolution or omitted fields break at the API
  boundary by design.
- Multimodal resolver coverage must provide canonical extractor metadata;
  otherwise the stricter resolver correctly rejects underspecified evidence.
- Existing RunStore compiler behavior remains for #165, so this change does
  not claim its eventual removal.

## Migration Plan

1. Register group 83 and define the strict admission contract.
2. Add failing tests for every removed form and retain equivalent canonical
   resolver coverage.
3. Remove the compatibility forms and update the active schema/export surface.
4. Run the exact group-83 command; commit the source change before recording a
   local-only source-bound receipt.
