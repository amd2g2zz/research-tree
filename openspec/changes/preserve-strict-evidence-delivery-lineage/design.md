## Context

The canonical Alpha2 path is now ledger-backed: strict Finding Packs resolve
typed `EvidenceAnchor` values through a matching `EvidenceResolver`, Decisions
retain those evidence parents, and `CanonicalReadinessVerifier` checks the
resulting graph. `DeliveryCompiler` still runs only through the legacy
`RunStore` abstraction, accepts a projected readiness mapping, and builds its
output parents from the visible Brief/Target/Decision/Finding nodes. It does
not require the resolver that authorized those nodes, does not bind delivery
to a caller-observed ledger revision, and does not retain the exact evidence
refs in its output lineage.

The issue is a narrow vertical boundary. It must not absorb OracleRun/closure
work (#56), worker validation trust (#109), the semantic Human Research Report
rename (#62), or the integrated receipt (#112). Legacy Alpha1 readers remain
supported while the canonical path becomes fail-closed.

## Goals / Non-Goals

**Goals:**

- Provide a named `CanonicalDeliveryCompiler` facade that requires one
  `RunLedger` and an `EvidenceResolver` bound to that exact ledger.
- Require an explicit `expected_revision` on the canonical compile call while
  retaining the current readiness projection mapping as the input contract.
- Reuse the existing document builders, but add a strict preflight that
  re-resolves every Finding observation anchor and checks its direct parent
  lineage, current revision, Target, and Decision refs.
- Include exact evidence refs in both artifacts' `parent_refs` while retaining
  the existing technical and human payload schemas.
- Append the technical package and human delivery as one ledger transaction so
  a revision conflict or storage failure cannot leave a half-created pair.
- Keep `DeliveryCompiler(RunStore)` behavior and its `human-brief` compatibility
  kind unchanged; the later #62 change owns the public rename.

**Non-Goals:**

- No evidence schema, CAS, resolver, Finding Pack, Decision Ledger, or
  Readiness rule changes.
- No new search, orchestration, host adapter, OracleRun, acceptance, or report
  depth behavior.
- No migration of historic RunStore artifacts and no change to the legacy
  compiler's accepted arguments.

## Decisions

### 1. Add a canonical facade instead of silently upgrading legacy storage

`CanonicalDeliveryCompiler(ledger, resolver)` follows the existing
`CanonicalFindingPackCompiler`, `CanonicalDecisionLedgerCompiler`, and
`CanonicalReadinessVerifier` pattern. Its constructor rejects a resolver whose
`.ledger` is not the supplied `RunLedger`. The existing `DeliveryCompiler`
continues to accept `RunStore` and remains explicitly non-strict.

An alternative was to infer strictness from a generic `DeliveryCompiler`
constructor or from a readiness mapping. That would let callers accidentally
fall back to legacy storage and would make the evidence authority invisible at
the call site.

### 2. Require an expected run revision without creating a Readiness cycle

The canonical `readiness` argument remains the validated projection mapping
used by the current compiler. The compiler does not require a Readiness
artifact because `CanonicalReadinessVerifier` itself reads an existing
Technical Package to create that record; requiring it here would make the
first strict package impossible to produce. `expected_revision` is checked
during the final append; stale callers fail with the ledger conflict rather
than rendering against a moving graph.

An alternative was to require an exact Readiness artifact. That stronger
contract belongs to a later integrated delivery/acceptance slice and would
create a circular dependency in this issue.

### 3. Revalidate evidence immediately before output

For each supplied Decision, the compiler collects linked strict Finding Packs.
For each Finding observation it parses `EvidenceAnchor`, calls the matching
resolver, requires the resolved exact `ArtifactRef` to be a direct Finding
parent, and rejects legacy anchors, stale revisions, inactive evidence,
missing CAS content, selector failures, and foreign rounds. It also requires
the resolved refs to be present in the Decision's direct parents when the
Decision claims them. The preflight completes for both outputs before any
write.

An alternative was to trust the Finding/Decision payloads because their
canonical compilers already validate them. Direct ledger writers and later
revisions make that insufficient at the final delivery boundary.

### 4. Use one ledger transaction for the output pair

`RunLedger.append_artifact_batch` will append the technical package and human
delivery under one `expected_revision`, validating parents and incrementing the
run revision only after both rows and lineage events are prepared. The batch
API is intentionally generic but remains a small ledger primitive with no
schema change. The strict compiler uses it only after all semantic preflight
checks pass.

An alternative was two sequential `append_artifact` calls. That already avoids
partial writes for invalid evidence, but a concurrent revision conflict or
second-write failure could leave a technical package without its co-primary
human artifact.

### 5. Preserve strict lineage without changing delivery payload schemas

Typed strict anchors remain in the Finding records rendered by the technical
package, while both output artifacts retain every resolved evidence ref as an
immutable direct parent. The existing technical traceability and human payload
schemas remain unchanged so the current Readiness reader can consume a newly
compiled package. The output kind remains `human-brief` until
#62 deliberately performs the compatibility rename.

## Risks / Trade-offs

- **Strict delivery rejects old or manually appended graphs.** This is
  intentional; callers must use canonical compilers or repair the graph. The
  legacy path remains available for historical reads.
- **Re-resolving evidence costs additional CAS/ledger reads.** Delivery is a
  correctness boundary; cache only within one compile and never weaken exact
  revision checks.
- **Batch append adds a ledger API surface.** Keep it typed by immutable
  artifact tuples, test parent ordering/conflict/rollback, and use it only for
  the two-output strict pair.
- **The Human Research Report rename remains pending.** Document the
  compatibility boundary and leave #62 as the owner of kind/template changes.

## Migration Plan

1. Land the strict facade, batch primitive, and focused tests on an issue-only
   branch.
2. Existing RunStore callers continue unchanged; no data migration is needed.
3. Canonical callers switch to `CanonicalDeliveryCompiler` when the strict
   Finding/Decision graph and readiness projection are available.
4. If the strict path must be rolled back, stop invoking the facade; immutable
   ledger history remains readable and no legacy artifact is rewritten.
5. #112 later verifies the clean-dev graph and reconciles the registries; it is
   not part of this change.

## Open Questions

- #62 will decide the final public field name and artifact kind for the human
  delivery; this change deliberately preserves the current compatibility kind.
