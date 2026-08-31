## Why

The optional assurance workflow is the first retained Finding Pack consumer
that still writes through `RunStore` and revises a decision with the legacy
`DecisionLedgerCompiler`. The complete #165 inventory also finds retained
legacy authoring, feedback, tree-state, delivery, readiness, evaluation, and
compiler surfaces. Closing #165 after only assurance would leave the
prior-version runtime reachable and would misstate the retirement claim.

## What Changes

- Retire the full #165 legacy runtime in ordered H--M packets recorded in
  `inventory.md`, using direct canonical implementations where the current
  Alpha2 contract retains that capability and delete-only retirement where it
  does not.
- Packet H replaces the public `AssuranceStrategySelector` and
  `AssuranceAdapterRunner` with direct `RunLedger` implementations named
  `CanonicalAssuranceStrategySelector` and `CanonicalAssuranceAdapterRunner`.
- Every ordinary replacement write requires an explicit expected run revision.
  Packet K adds one dedicated `RunLedger` transaction for feedback successors:
  it compares the predecessor revision, creates one successor run, and writes
  ordered successor and predecessor artifact batches in one SQLite commit.
  It accepts no callback or arbitrary SQL and introduces no compatibility store.
- Migrate retained consumers to direct canonical contracts before removing
  their legacy compiler, service, export, test fixture, documentation, and
  generated-package references.
- Finish with a structural absence proof that active runtime, CLI, schema,
  test, documentation, and package sources expose no `RunStore`,
  `FindingPackCompiler`, or `DecisionLedgerCompiler` compatibility surface.

## Non-Goals

- Do not alter existing `RunLedger` write methods or schema, create a storage
  adapter, retain an alias, or introduce a dual store, fallback parser,
  migration, or compatibility reader. The dedicated Packet K transaction is
  limited to one new successor and its exact predecessor, and is not a general
  transaction or callback surface.
- Do not delete a legacy surface while a retained current runtime consumer is
  still present; each packet must first establish its direct canonical
  replacement or retire the complete unreachable feature boundary.

## Impact

Packet H is limited to `assurance.py` and its root exports. The following
packets deliberately cover the remaining surfaces listed in `inventory.md`;
all are delivered through this one #165 branch and one PR as independently
tested commits. Raw verification receipts remain local and ignored.
