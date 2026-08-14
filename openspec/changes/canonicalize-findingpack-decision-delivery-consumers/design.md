## Context

`RunStore` and `FindingPackCompiler` are retained compatibility surfaces. The
decision, delivery, and strict-delivery consumers named by issue #180 must
instead construct the canonical graph directly: a `RunLedger` run, the
prerequisite artifact graph, evidence recorded through the ledger, a matching
`EvidenceResolver`, and a Finding Pack compiled by
`CanonicalFindingPackCompiler`.

## Goals / Non-Goals

**Goals:**

- Keep each fixture self-contained and rooted in one `RunLedger`.
- Use `CanonicalFindingPackCompiler` for every Finding Pack under test.
- Retain the consumer-facing values and assertions needed by decision,
  delivery, and strict-delivery tests.
- Preserve assurance behavior coverage with the private legacy `RunStore`
  fixture until #165 decides a canonical replacement or whole-runtime
  retirement, and keep readiness on that fixture only until #181 migrates it.
- Make no writes to a task registry or source-bound receipt before the #175
  group-78 delivery queue is reachable from `dev`.

**Non-Goals:**

- No production runtime changes or public API changes.
- No changes to `RunStore`, retired compilers, runtime adapters, aliases,
  fallback parsers, runtime old-state helpers, historical migration, or compiler deletion.
- No test-only `RunLedger`/`RunStore` bridge, dual store, or weakened assurance
  assertion.

## Decisions

### 1. Use one direct canonical fixture helper

A small test-only helper will append only the prerequisite canonical ledger
artifacts, record a source through the canonical evidence repository, create a
resolver bound to that ledger, and invoke `CanonicalFindingPackCompiler`.
Consumers receive the same kinds of artifacts they require without copying or
migrating a `RunStore` snapshot.

### 2. Isolate retained legacy test coverage from canonical consumers

The three canonical suites retain their behavioral assertions without moving
test ownership to a runtime-facing module. Assurance no longer imports the
migrated decision fixture, and readiness no longer imports the migrated delivery
fixture. They share a private test-only legacy fixture because both exercise
`RunStore`; #181 removes readiness from that boundary. The helper is not a
runtime facade, adapter, migration, or bridge, and canonical suites do not import it.

### 3. Prove the migration with focused regression guards

Focused tests must execute the three retained canonical consumers against the
direct fixture, and static assertions must show that those suites neither
import nor construct the retired Finding Pack compiler via a `RunStore`
fixture. The assurance suite is intentionally excluded from that static check
and is run as a legacy-runtime regression.

## Risks / Trade-offs

- The delivery fixture has a high test-only blast radius, so its exact return
  shape remains stable while setup changes under it.
- Hand-constructing prerequisite canonical artifacts can drift from expected
  schemas; use the existing canonical compiler and focused/full regressions to
  keep the graph valid.
- The assurance adapter APIs call `RunStore.load_round()` and append without a
  ledger revision; their blocked path constructs legacy `DecisionLedgerCompiler`.
  Treating them as canonical without a runtime replacement would create the
  prohibited bridge or discard behavior coverage.
- Readiness remains legacy only until #181, preventing #180's delivery migration
  from becoming a hidden cross-issue behavior rewrite.
- Registry and receipt ownership remains queued behind #175 to avoid a
  concurrent registry conflict.

## Migration Plan

1. Record a failing focused test that detects retained legacy fixture use.
2. Add the minimum direct canonical fixture helper and switch the three
   canonical consumers; isolate assurance/readiness legacy test setup.
3. Run canonical focused tests plus assurance/readiness regression, relevant full
   tests, lint, OpenSpec, package, and delivery gates.
4. After #175's queue is merged, rebase and write only the required
   source-bound registry receipt before delivery.
