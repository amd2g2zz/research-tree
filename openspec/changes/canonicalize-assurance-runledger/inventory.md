# #165 H–M Runtime Retirement Inventory

This is a read-only inventory of the `origin/dev` baseline at
`564372bb37d7e6df56f5e079337f1f0c8f094`. It distinguishes direct runtime
dependencies from historical governance records. A packet cannot delete a
source, export, fixture, or compiler until its listed canonical replacement is
implemented and its direct consumers are absent.

## Evidence Method

- GitNexus finds 14 direct `RunStore` importers and 69 upstream symbols through
  depth three. `FindingPackCompiler` and `DecisionLedgerCompiler` each have 6
  direct importers; `RunLedger` has 14 direct importers and 68 symbols through
  depth three.
- `RunLedger.append_artifact` has HIGH risk: 25 direct callers and 110 symbols
  through depth three. The packets consume this API but do not modify it.
- The public CLI has no `RunStore` import or command. `RunStore` references in
  `docs/specs/` and `openspec/changes/archive/` are historical, not live
  runtime contracts.

## Packet H — Assurance

| Direct consumer | Canonical replacement | Action |
| --- | --- | --- |
| `assurance.py:AssuranceStrategySelector` | none yet | Replace with `CanonicalAssuranceStrategySelector(RunLedger)` and explicit revision writes. |
| `assurance.py:AssuranceAdapterRunner` | none yet | Replace with `CanonicalAssuranceAdapterRunner(RunLedger, EvidenceResolver)`; block decisions through `CanonicalDecisionLedgerCompiler`. |
| `tests/test_assurance_adapters.py` and `tests/legacy_runstore_fixture.py` | `tests/canonical_finding_fixture.py` | Rebuild the strategy/selection fixture directly in one canonical ledger, then remove the private legacy fixture only after it has no importers. |
| root exports | canonical assurance exports | Remove old class exports with no alias. |

Expected changed review surface: 1,032 runtime + 417 test + 186 fixture lines;
estimated diff 500–750 lines across 6–8 files.

## Packet I — Authoring Graph

| Direct consumer | Canonical replacement status | Required action |
| --- | --- | --- |
| `application.py` helper facade | direct `RunLedger` primitives exist | Delete the unused facade or replace each caller with direct ledger operations; do not wrap it as a compatibility API. |
| `intake.py:InputIntakeService` | none | Implement direct ledger intake writer, then retire old class/export and `test_context_intake.py` fixture. |
| `intent.py:IntentModelCompiler`, `WorkingBriefCompiler` | none | Implement direct canonical writers with explicit revisions, then retire old compilers/export and `test_intent_and_brief.py`. |
| `decision_map.py:BlueprintTargetCompiler` | none | Implement direct canonical target compiler, then migrate its tests and downstream work-item/ledger callers. |
| `work_items.py` compiler/planner/status services | none | Implement direct canonical work-item writers before deleting old services. |
| `alignment_handoff.py:initialize_research_from_alignment` | `AlignmentProtocol` is ledger-based but not equivalent | Rewrite directly over canonical artifacts after packet K’s tree-state replacement; no adapter. |

Direct test consumers: `test_context_intake.py`, `test_intent_and_brief.py`,
`test_decision_map.py`, `test_work_items.py`, and `test_alignment_controller.py`.
Expected review surface: 3,180 runtime + 2,349 direct-test lines; estimated
diff 2,000–3,000 lines across 13–16 files.

## Packet J — Delivery, Readiness, Evaluation, and Compilers

| Direct consumer | Canonical replacement | Required action |
| --- | --- | --- |
| `ledger.py:FindingPackCompiler` | `CanonicalFindingPackCompiler` | Migrate all remaining authoring/tree-state callers in I/K, then delete class and export. |
| `ledger.py:DecisionLedgerCompiler` | `CanonicalDecisionLedgerCompiler` | Migrate H/I consumers, then delete class and export. |
| `delivery.py:DeliveryCompiler` | `CanonicalDeliveryCompiler` | Migrate remaining legacy delivery callers and remove the union base path. |
| `readiness.py:ReadinessVerifier` | `CanonicalReadinessVerifier` | Migrate remaining callers and remove the union base path. |
| `evaluation.py:BlueprintEvaluationSuite` | partial: it accepts `RunLedger`, but no canonical-only class | Split it to a direct ledger implementation; then delete the RunStore branch. |

Direct test consumers: `test_strict_delivery_lineage.py` (negative legacy
constructor assertions), `test_strict_evidence_decision_boundary.py` (negative
legacy compiler/readiness assertions), plus the authoring tests in packet I.
After deletion they become absence tests, not compatibility tests.

Expected review surface: 6,107 runtime + 1,431 direct-test lines; estimated
diff 2,500–3,500 lines across 14–18 files.

## Packet K — Feedback and Tree-State

| Direct consumer | Canonical replacement status | Required action |
| --- | --- | --- |
| `feedback.py:FeedbackRoundService` | none | Replace successor-round/copy behavior with direct immutable ledger artifacts and one restricted predecessor-CAS/successor-create transaction; prohibit the temporary `RunStore(staged_root)` path. |
| `tree_state.py:ResearchTreeStateService` | none | Replace with direct canonical state artifacts and explicit revisions. |
| `recursive_search.py:RecursiveResearchCoordinator` tests | no canonical tree-state service | Migrate after tree-state replacement; the coordinator must never receive a compatibility store. |
| `alignment_handoff.py` | depends on tree-state replacement | Migrate after the canonical state writer exists. |

Direct test consumers: `test_feedback_rounds.py`, `test_recursive_search.py`,
and `test_alignment_controller.py`. Expected review surface: 1,589 runtime +
2,196 direct-test lines; estimated diff 1,500–2,500 lines across 8–11 files.

## Packet L — Active Contracts and Generated Hosts

| Surface | Classification | Required action |
| --- | --- | --- |
| `README.md`, `references/research-tree-architecture.md`, `docs/adr/ADR-001-runtime-foundation.md` | active | Remove current RunStore claims once the runtime source is absent; replace with current RunLedger contract where supported. |
| umbrella registries and tasks | active governance | Register one #165 packet sequence and final absence proof; do not create child issues, branches, or PRs. |
| `packages/*/references/research-tree-architecture.md` | generated | Regenerate from `references/`; never edit directly. |
| `docs/specs/`, archived changes, completed receipts | historical | Preserve as audit material; validate source revision reachability rather than rewriting history. |

Estimated diff: 500–900 source documentation/registry lines and 906 regenerated
package lines across 9–14 files.

## Packet M — Final Absence Proof

Only after H–L have eliminated their consumers:

1. Delete `storage.py:RunStore` (264 lines), the legacy portions of
   `ledger.py` (roughly 350 lines), legacy delivery/readiness branches, and
   their root exports.
2. Delete `tests/legacy_runstore_fixture.py` and `tests/test_runtime_foundation.py`;
   convert remaining negative tests to absence checks.
3. Prove no runtime source, test, active documentation, schema, public export,
   generated package, or CLI surface names `RunStore`, `FindingPackCompiler`,
   or `DecisionLedgerCompiler`.

`test_legacy_import_removal.py`, `test_runstore_scheduler_parent_acceptance.py`,
and historical OpenSpec receipts may retain their terms only as historical
source-bound audit evidence; they are not runtime consumers.

## Single-PR Estimate and Gate

The direct inventory covers 12,092 relevant runtime lines and 6,343 direct
test/fixture lines (18,435 total), before active contracts and generated
packages. A complete single-PR retirement is therefore estimated at 35–50
changed files and roughly 7,000–10,000 changed lines after replacements and
deletions. It is one branch and one PR, but must be committed and receipt-bound
per H–M packet. No packet claims #165 completion until M’s structural absence
proof and full delivery gates pass.
