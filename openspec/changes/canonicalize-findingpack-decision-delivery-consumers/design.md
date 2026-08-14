## Context

`RunStore` and `FindingPackCompiler` are compatibility surfaces. The named
consumers must construct a `RunLedger` graph with canonical evidence resolution
and `CanonicalFindingPackCompiler`.

## Goals / Non-Goals

**Goals:**

- Preserve decision, delivery, and strict-delivery assertions on direct ledger
  fixtures.
- Retain assurance behavior and readiness's pre-#181 behavior on an isolated
  legacy test fixture.
- Write registry/receipt evidence only after #175 is reachable.

**Non-Goals:**

- No production API or runtime change, legacy compiler deletion, or history
  migration.
- No runtime adapter, old-state helper, fallback, alias, dual store, or test
  bridge.

## Decisions

### Direct Canonical Fixture

One test helper appends prerequisite canonical artifacts, records a source,
binds an `EvidenceResolver`, and compiles the Finding Pack without a migrated
`RunStore` snapshot.

### Isolated Legacy Boundary

Assurance no longer imports the migrated decision fixture and readiness no
longer imports the migrated delivery fixture. Both use a private fixture only
for their retained `RunStore` behavior; #181 removes readiness from it. Generic
immutable sample data stays in the canonical delivery test, not legacy state.

### Regression Proof

Focused tests exercise the three canonical suites, while static checks reject
`FindingPackCompiler`, `RunStore`, migration helpers, and legacy fixture paths
in those suites. Assurance/readiness run separately as legacy regressions.

## Risks / Trade-offs

- The delivery fixture has a high test-only fan-out; preserve its return shape.
- Canonical prerequisite hand construction can drift; use compilers and focused
  plus full regressions.
- Treating assurance as canonical would require the prohibited adapter; #165
  owns replacement or retirement.

## Migration Plan

1. Record focused RED evidence for retired fixture use.
2. Add direct canonical fixtures and isolate unchanged legacy test setup.
3. Run focused/full tests, lint, OpenSpec, package, and delivery gates.
4. Rebase after #175, then record the source-bound registry receipt.
