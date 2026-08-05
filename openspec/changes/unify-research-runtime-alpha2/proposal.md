## Why

Alpha1 established the product vocabulary and three-host packaging, but it also introduced overlapping completion authorities, unverifiable validation claims, structural-only report gates, fixed alignment branching, and split runtime state. These defects directly permit premature handoff, shallow research, unsupported conclusions, inconsistent host behavior, and false completion, so alpha2 must unify the execution contract before adding more research features.

## What Changes

- Establish one `ResearchRunCoordinator` as the only authority for research lifecycle transitions, Decision Slot closure, delivery readiness, and completion.
- Replace split filesystem and host-specific writable state with a run-scoped SQLite RunLedger plus content-addressed storage for large artifacts.
- Introduce resolvable multimodal Evidence Artifacts, executable `OracleRun` records, and non-bypassable `SlotClosureAssessment` artifacts.
- Replace fixed alignment branch ordering with a persisted, evidence-bearing strategy that selects reconnaissance, one open question, constructive disagreement, or explicit handoff confirmation.
- Make requester corrections transactional: invalidate dependent alignment,
  strategy, handoff, and delivery revisions before any stale plan can continue.
- Refactor the global recursive completion state into a local `AdaptiveResearchPolicy` that proposes evidence-triggered growth, pruning, validation, and method switching without owning canonical state.
- Define a versioned Host Event Protocol; Codex, Claude Code, and Hermes adapters translate native lifecycle events but cannot weaken evidence or completion rules.
- Compile a Technical Research Package and a professional Human Research Report from the same Decision Ledger and require explicit acceptance of their exact revisions.
- Add causal traces, replay, recovery, provider-failure handling, cross-host parity checks, and release-grade black-box evaluation.
- Separate observed host/model behavior from causal attribution; require a
  controlled comparison before assigning a model- or host-specific cause.
- Establish an explicit documentation authority registry and lifecycle so normative, generated, historical, operational, and evaluation documents cannot silently conflict.
- Establish one governed evaluation asset model that separates cases, harnesses, hidden-oracle interfaces, baselines, scored results, expert reviews, raw transcripts, and disposable run output.
- Enforce repository layout boundaries among authoring sources, generated packages, installed host copies, runtime state, evaluation assets, build products, and caches.
- **BREAKING** Retire adapter-owned completion, Markdown byte/heading gates, manual slot closure, and writable `.research-tree-native` / `.research-tree-hermes` completion state.
- **BREAKING** Rename the `Human Brief` delivery contract to `Human Research Report`; legacy artifacts remain importable but cannot satisfy alpha2 completion without revalidation.

## Capabilities

### New Capabilities

- `mutual-alignment`: Persistent human-agent belief revision, bounded reconnaissance, constructive disagreement, one-prompt turns, and explicit autonomous handoff.
- `durable-research-runtime`: SQLite-backed immutable run lineage, attempts, recovery, migration, and a single lifecycle authority.
- `evidence-verification`: Resolvable multimodal evidence, provenance independence, executable oracles, and auditable Decision Slot closure.
- `adaptive-research-execution`: Decision-centric action selection, evidence-triggered growth, conservative pruning, contradiction handling, and autonomous long-horizon replanning.
- `host-event-protocol`: Host-neutral lifecycle events with platform-specific Codex, Claude Code, and Hermes execution adapters.
- `semantic-research-delivery`: Decision-Ledger-derived technical and human reports, readiness verification, and revision-bound human acceptance.
- `runtime-observability`: Causal transition traces, why-action and why-not-complete explanations, replay, reconciliation, and safe provider diagnostics.
- `research-quality-evaluation`: Adversarial, cross-host, hidden-oracle, independent-implementation, and expert-review release gates.
- `documentation-governance`: Document authority, ownership, lifecycle, supersession, generated-copy provenance, terminology, and link integrity.
- `evaluation-asset-governance`: Canonical evaluation namespaces, schemas, provenance, oracle separation, retention, redaction, and reproducible entry points.
- `repository-layout-governance`: Enforced source, generated, installation, runtime, evaluation, build, cache, and historical path boundaries.
- `canonical-runtime-contract`: Exact versioned entity envelopes, lifecycle transitions, Decision Slot and Work Item schemas, leases, idempotency, coordinator APIs, and projection boundaries.
- `autonomous-tool-and-interaction`: Typed heterogeneous intake, capability/permission profiles, self-directed uncertainty handling, bounded alignment turns, autonomy envelopes, and inspectable growth/stop/prune decisions.
- `implementation-release-contract`: Requirement-to-code/test/evidence traceability, installable public contracts, reversible migration, immutable release manifests, pre-registered quality gates, and observable Definition of Done.
- `canonical-schemas`: Checked-in versioned schemas, examples, validators, reference cardinality, and compatibility matrices for every canonical entity.
- `lifecycle-state-machine`: Closed run-state transition matrix with explicit pause, resume, authority-block, supersession, acceptance, and replay semantics.
- `worker-orchestration`: Bounded worker assignments, leases, heartbeats, fan-out/fan-in independence, partial outputs, retry, cancellation, and no-progress scheduling.
- `research-acquisition`: Method/tool registry, source snapshots, derivative provenance, multimodal selectors, and typed acquisition fallback.
- `insight-synthesis`: Versioned InsightDigest artifacts that classify facts, inferences, recommendations, contradictions, gaps, and action triggers.
- `security-execution-boundary`: Sandboxed tool/oracle execution, path and network allowlists, secret redaction, licensing, and safe evidence handling.
- `release-evidence`: Frozen evaluation manifests, executable metric definitions, absolute safety gates, blinded review, and offline-verifiable release bundles.
- `skill-activation-integrity`: Host-specific activation proofs, stale-install diagnostics, explicit context-injection boundaries, and cross-host black-box activation evidence.

### Modified Capabilities

None. The repository has no existing OpenSpec capability specifications; alpha2 formalizes the current product contract as new capabilities.

## Impact

- Core modules affected: storage, alignment graph and handoff, Finding Pack and Decision Ledger compilation, scheduler/orchestration, recursive search, readiness, delivery, evaluation, feedback, CLI, lifecycle tracing, canonical coordinator, event ingestion, CAS, migration, and contract validators.
- Runtime entry points affected: source-checkout CLI, package build scripts, native execution adapter, Hermes execution adapter, and lifecycle hooks.
- Distribution affected: separate Codex, Claude Code, and Hermes skill packages and their host-specific references, setup, and compatibility tests.
- Repository governance affected: README, PRODUCT, OpenSpec, ADRs, legacy RT specifications, generated package documentation, evaluation assets, `.gitignore`, build output, and top-level path policy.
- Delivery governance affected: machine-readable schemas, state-transition matrices, API/CLI contracts, host capability matrices, migration manifests, release manifests, and requirement-to-evidence traceability.
- New planning artifacts: checked-in JSON schemas and executable examples, SQLite v1 DDL, lifecycle and error registries, host capability matrix, compatibility matrix, documentation/evaluation/repository registries, delivery coverage matrix, and task execution registry.
- Data affected: alpha1 filesystem rounds, alignment SQLite databases, native/Hermes checkpoints, Finding Packs, reports, and delivery names require explicit migration dispositions.
- External tracking: GitHub milestone `alpha2`, Epic #67, and implementation
  issues #53-#73 define the mission, back story, dependencies, governance, and
  release evidence.
