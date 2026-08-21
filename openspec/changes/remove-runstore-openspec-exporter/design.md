## Context

Issue #171 established that the retained Finding Pack consumer migrations are
complete at group 81. The remaining `OpenSpecExporter` path is intentionally
separate: it owns a complete RunStore-only projection module, a dedicated
behavior suite, and an E2E test whose package fixture directly invokes the
retired `FindingPackCompiler`. No canonical OpenSpec authoring runtime exists
or is requested by this issue.

## Goals / Non-Goals

**Goals:**

- Remove the exporter module and all public names rather than retaining an
  error shim or hidden import path.
- Replace legacy exporter behavior coverage with a small absence/current-runtime
  regression.
- Remove the E2E consumer together with its only legacy exporter fixture; keep
  canonical runtime coverage in the already-canonical Finding Pack suites.
- Remove active documentation and registry claims, then regenerate checked-in
  host packages from their authoritative reference source.
- Register issue #176 as group 82 depending on verified group 81.

**Non-Goals:**

- Creating a replacement exporter, adapter, bridge, alias, fallback parser,
  compatibility reader, migration, or dual-state path.
- Reading, importing, transforming, moving, repairing, or deleting user-owned
  RunStore or OpenSpec data.
- Changing #168 or `tests/test_assurance_adapters.py`, which remains the #165
  reserved legacy-fixture boundary.

## Decisions

### Delete the entire writer boundary

`openspec.py` is wholly owned by the retired projection. Removing the module,
root exports, dedicated behavior suite, and E2E consumer makes the cutover
unambiguous. A retained exception, no-op writer, import alias, or rejection
facade would still publish an integration boundary and is therefore excluded.

### Make absence the regression contract

The focused regression checks that the root package no longer publishes the
retired names, `research_tree.openspec` cannot resolve, no runtime source
imports it, the dedicated legacy test and E2E consumer are absent, and the
current canonical ledger/finding interfaces remain published. It also checks
active authority and generated packages for stale exporter claims.

### Preserve only historical records

`docs/specs/` and `docs/reviews/` are governed historical directories and may
retain immutable audit context. Active product, operational, reference, and
umbrella-registry sources must stop advertising the exporter. Their generated
host-package copies are regenerated from `references/` rather than hand-edited.
Verified group receipts are also historical: a missing current Python
entrypoint remains valid only when the receipt's source revision is an ancestor
of the current revision and Git resolves that exact path there. A missing
entrypoint without that reachable, source-bound proof remains a governance
violation.

### Register a planned source removal before verification

Group 82 depends only on #171's verified group 81 and has an exact focused
acceptance command. It remains planned until the source removal is committed
and a source-bound verification receipt can be recorded; raw command output is
local and ignored.

## Risks / Trade-offs

- **Existing callers lose imports**: deliberate breaking cutover, recoverable
  only by reverting the release revision.
- **Historical documents still describe the old path**: they are governed as
  historical audit material, not current contracts.
- **Deleting the E2E test reduces old-path coverage**: it removes a retired
  writer consumer; retained canonical suites continue to validate the current
  runtime.

## Migration Plan

1. Register group 82 and define this current-only removal contract.
2. Add a failing absence/current-runtime regression.
3. Delete the writer, public exports, legacy tests, E2E consumer, and active
   authority claims; regenerate packages from the changed reference source.
4. Run the exact group-82 command, strict OpenSpec, governance, documentation,
   package, diff, and full test checks. Commit source removal before recording
   any source-bound verification receipt.
