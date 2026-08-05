## Context

Alpha1 contains two partially overlapping post-handoff systems. The structured product path persists Inputs, Intent Models, Working Briefs, Blueprint Targets, Work Items, Finding Packs, Decision Ledger entries, readiness records, and compiled deliveries. A newer recursive path separately tracks Decision Slot evidence, frontier nodes, validation strings, report manifests, and completion. Native and Hermes adapters add further host-local checkpoints and report gates.

This split lets a host batch, recursive state, or shape-valid Markdown claim completion without passing the stronger Decision Ledger and Readiness contracts. It also makes crash recovery and diagnosis ambiguous because alignment SQLite, filesystem RunStore, native state, Hermes state, and report files may disagree.

Alpha2 is a local, Python 3.11+ skill runtime for Codex, Claude Code, and Hermes. It must remain dependency-light, support Windows and POSIX hosts, preserve strict UTF-8 without BOM, tolerate long-horizon execution without cost-based termination, and retain separate host package formats. Users collaborate with the agent before strategy handoff; after explicit confirmation, normal research decisions are autonomous until authority, safety, feasibility, or final acceptance requires human input.

## Goals / Non-Goals

**Goals:**

- Make one persisted coordinator the sole lifecycle and completion authority.
- Store all run-scoped lineage, attempts, evidence metadata, oracle outcomes, and host events in SQLite with deterministic recovery.
- Make evidence and validation references resolvable and tamper-evident across text, code, experiments, user inputs, documents, and images.
- Choose alignment and research actions from current decision deficits rather than fixed dialogue or wave counts.
- Preserve platform-native delegation while enforcing identical semantic contracts on all hosts.
- Compile professional, traceable technical and human deliveries from canonical decisions and verify them with structural, semantic, implementation, and human gates.
- Provide causal explanations and black-box evidence strong enough to decide whether alpha2 is releasable.
- Make documentation authority and lifecycle explicit enough that contributors and host agents cannot mistake generated, historical, or operational material for a canonical product contract.
- Make evaluation evidence reproducible by separating versioned definitions from harnesses, hidden-oracle interfaces, baselines, human reviews, transcripts, and disposable outputs.
- Enforce repository path ownership so authoring sources, generated packages, installations, runtime state, and build artifacts cannot silently overlap.
- Make the proposal implementation-ready: no central noun, transition, command, failure state, or release claim may remain defined only by an informal sentence.

**Non-Goals:**

- Replacing all domain components with a new global tree or graph database.
- Guaranteeing automated truth for every external claim.
- Using LDA, embeddings, information gain, PageRank, or an LLM judge as a sole decision oracle.
- Requiring a fixed number of questions, workers, sources, waves, headings, bytes, or URLs.
- Stopping research because of token or monetary cost; operational limits create resumable checkpoints.
- Permanently supporting multiple writable state authorities or dual-write completion paths.

## Decisions

### 1. The structured product path is authoritative

`ResearchRunCoordinator` will compose the existing Intent, Blueprint Target, Work Item, Finding Pack, Decision Ledger, Readiness, Delivery, Evaluation, and Feedback services. It alone transitions a run among alignment, autonomous research, synthesis, readiness, delivery, acceptance, completion, supersession, and authority-blocked states.

The recursive search module will not replace these services. Its slot status, report manifest, and completion fields are removed from canonical semantics.

**Alternatives considered:**

- Continue patching each adapter: rejected because semantic drift and bypass paths remain.
- Make recursive-search state authoritative: rejected because it loses exact Blueprint, Decision Ledger, readiness, and implementation-evaluation lineage.
- Keep multiple authorities and reconcile them: rejected because reconciliation cannot prove which completion claim was legitimate.

### 2. SQLite is the run ledger; large content uses a CAS

One workspace database stores runs, immutable artifact revisions, parent references, events, action attempts, evidence metadata, oracle runs, and host events. The implementation enables foreign keys, WAL, full synchronization, busy timeout, and optimistic expected-revision checks. Only the coordinator writes canonical transitions; workers produce candidate artifacts for ingestion.

Large source snapshots, binaries, images, and experiment output are stored under a SHA-256 content-addressed directory. The ledger records the digest, media type, size, locator, acquisition details, and selectors.

**Alternatives considered:**

- Keep filesystem JSON as the final store: rejected because cross-file atomicity and concurrent state claims are difficult to enforce.
- Store large blobs directly in SQLite: rejected because it increases lock duration and database churn without improving semantic integrity.
- Use a dedicated graph database: rejected because the workload is local, transactional, and already artifact-centric.

### 3. Distinct graph boundaries remain distinct

The system keeps separate structures for intent/brief lineage, the current work dependency DAG, typed evidence relations, and decisions-to-implementation. Cross-layer `ArtifactRef` lineage connects them. A local Research Action Graph may project one Decision Slot's search history, but it is rebuildable and cannot become global product state.

**Alternative considered:** one heterogeneous multigraph for every relation. Rejected because intent supersession, work acyclicity, evidence contradiction cycles, and rollout dependencies have incompatible invariants.

### 4. Evidence is an artifact, and validation is an executed oracle

An Evidence Artifact has an immutable content reference, acquisition method, media type, provenance, independence group, applicability, and limitations. An Evidence Anchor references an exact artifact revision and selector: repository revision/path/symbol/line, document page/section, image region, input revision, source snapshot fragment, or experiment result field.

Workers may submit observations but cannot produce an authoritative validation verdict. `OracleRun` binds the current OracleSpec and attempt to inputs, method, environment, tool events, result artifacts, evaluator, verdict, and limitations. `SlotClosureAssessment` verifies required evidence classes, independence, counterevidence, contradiction disposition, oracle status, fallback, and reversal conditions before issuing a closure token.

The coordinator derives the active P0 Slot set from one exact, current Blueprint
Target artifact. A single Slot token never satisfies the run-level `p0_closure`
obligation. The core evaluator deterministically aggregates the latest assessment
for every active P0 Slot into a persisted `P0ClosureAggregate`; only a passed
aggregate digest may satisfy that obligation. Rebinding a newer Blueprint Target
immediately opens a new aggregate and prevents tokens issued for the older Slot set
from satisfying completion.

### 5. Alignment is an action policy with semantic readiness

Each alignment planning step persists one candidate action and attempt. The policy compares:

- reconnaissance value for agent-verifiable uncertainty;
- question value for high-impact requester-only preference or authority;
- debate value when material human and agent beliefs conflict;
- confirmation eligibility when the strategy projection is semantically ready.

Scoring records impact, researchability, human exclusivity, expected ambiguity reduction, decision consequence, cognitive load, and repetition. It is an explainable policy, not a truth probability. User-facing turns contain a short mirror, relevant evidence or counterargument, consequence, and at most one open prompt. Explicit confirmation is bound to the displayed digest.

### 6. Adaptive research is local, evidence-triggered, and decision-centric

`AdaptiveResearchPolicy` consumes open Decision Slots, verified Finding Packs, Insight Digests, closure deficits, and prior action outcomes. It emits typed actions: landscape, deep dive, adversarial check, validation, and method switch.

Growth occurs only when evidence exposes a narrower gap, competing hypothesis, invalid premise, failed oracle, or method limitation. Pruning marks optional duplicate, dominated, superseded, or decision-neutral actions without deleting history. P0 obligations, unresolved contradictions, counterevidence, and required validation are never pruned solely for low score.

Expected value ranks candidate actions. Realized delta is a vector of evidence-class coverage, provenance independence, contradiction state, oracle state, implementation uncertainty, and decision closure. C4.5-style gain ratio may normalize branch proliferation; C5-style pessimistic pruning may defer repeated no-change optional work; boosting-like reweighting occurs only after a ledger-observable oracle failure.

### 7. Hosts translate events and own no business state

The versioned Host Event Protocol includes dispatch requested, attempt started, finding submitted, review completed, provider failed, attempt unknown, retry requested, and worker finished. Every event identifies run, round, Decision Slot, action, attempt, host, and expected ledger revision.

Codex and Claude Code use native subagent and question mechanisms. Hermes may use delegation, goals, Kanban, and lifecycle hooks. Hooks remain fail-open observability/wake-up mechanisms and cannot verify evidence or complete work. Provider failures persist safe metadata and move attempts to retryable or unknown states; they never imply task or run completion.

### 8. Delivery is compiled, co-primary, and revision-accepted

The existing DeliveryCompiler remains the canonical renderer. It produces a Technical Research Package and Human Research Report from the same exact Working Brief, Blueprint Target, Finding Packs, Decision Ledger entries, and Readiness record. Arbitrary worker Markdown and adapter byte/heading gates are removed.

The Human Research Report is not a courtesy summary. It must explain the understood problem, evidence, recommended direction, alternatives, consequences, risks, applicability, unknowns, and implementation meaning at professional depth. A `DeliveryAcceptance` artifact binds explicit user acceptance to exact delivery revisions. Rejection creates evidence-bearing follow-up work or a successor round.

### 9. Completion is a conjunction of independently checkable facts

A run completes only when:

1. the run is in canonical `awaiting_acceptance` after research and readiness obligations pass;
2. every active P0 Decision Slot has a valid closure token;
3. no blocking Insight Digest signal or unresolved authority boundary remains;
4. the Technical Research Package and Human Research Report are compiled from the closed Decision Ledger;
5. Readiness gates pass at the selected risk tier;
6. required independent implementation or hidden-oracle evaluation passes; and
7. the user explicitly accepts the exact delivery revisions.

Empty frontier, exhausted local capacity, completed worker waves, hook success, report existence, or generic acknowledgement are not completion conditions. Alpha1 states `aligned`, `searching`, `delivery_pending`, `complete`, and `unknown` map respectively to `handoff_pending`, `autonomous_research`, `delivery_pending`, `completed`, and attempt-level `unknown`; they are never accepted as new canonical state names.

### 10. Traces explain causes; black-box cases decide release

Every transition records prior/next revision, cause event, decision inputs, score components, validation result, and reason. CLI projections provide `explain-run`, `why-action`, `why-not-complete`, `replay`, and `reconcile-host`. Logs redact prompts, secrets, credentials, and raw provider details.

Alpha2 release evaluation uses versioned ambiguous, adversarial, repository-backed, multimodal, recursive, provider-failure, crash, and feedback cases. Hidden oracles, independent implementation runners, and blinded experts measure intent fidelity, unsupported claims, P0 coverage, contradiction handling, reproducibility, false completion, rediscovery burden, implementation success, recovery, host parity, and human acceptance.

### 11. Documentation has an authority registry and explicit lifecycle

One documentation index classifies every surface as normative, active-change, generated, historical, operational, or evaluation evidence. Each class records its canonical source, audience, owner, lifecycle status, update trigger, supersession behavior, and validation rule. PRODUCT and ratified OpenSpec/ADR decisions define active product and architecture contracts; README explains supported use; shared authoring references feed generated host packages; historical RT specifications remain traceable but cannot silently override active contracts.

Generated package documentation is never an authoring source. Build provenance and drift checks bind every generated copy to its canonical source. Link and terminology checks reject stale active guidance while allowing explicitly marked historical terminology.

### 12. Evaluation definitions and evaluation output have different lifecycles

Alpha2 selects one canonical evaluation namespace. Versioned cases, schemas, harness code, public fixtures, hidden-oracle interfaces, registered baselines, scored results, expert reviews, raw transcripts, and disposable output occupy non-overlapping governed paths. Every retained result binds the case version, implementation revision, host/package identity, command, environment, evaluator, and referenced artifacts.

Raw provider logs, secrets, hidden oracle bodies, and unredacted transcripts are not public evaluation fixtures. Retention, redaction, size, and ignore policies are enforced. The current `evaluation/cases/v1.json`, untracked `evaluation/experiences`, and ambiguous `evals/` root receive explicit migration dispositions before #55 or #64 can define release evidence.

### 13. Repository paths encode ownership and mutability

A machine-readable path registry classifies each top-level path and relevant subtree as authoring source, generated distribution, installed host copy, durable runtime state, evaluation source, evaluation output, build product, cache, or historical material. The registry defines owner, mutability, tracked status, distribution status, cleanup safety, and canonical generation command.

Clean-checkout checks run package builds, tests, supported local installation, and a sample research execution and then reject unexplained repository changes or unexpected roots. Migration is non-destructive for untracked user data: tooling reports and relocates only with explicit operator action.

### 14. Contracts are executable, not merely descriptive

The implementation starts with a versioned contract registry under `src/research_tree/contracts/` (or an explicitly ratified equivalent) for entity envelopes, enumerations, transition preconditions, error codes, and event payloads. Each contract has a strict validator, a canonical JSON example, and a negative example. The coordinator API and CLI are specified against those contracts; adapters are tested as translators into them.

The minimum implementation surface is explicit:

| Contract surface | Required implementation boundary | Required proof |
| --- | --- | --- |
| canonical state | `ResearchRunCoordinator` plus SQLite repository | transition matrix tests, stale-write and crash replay |
| evidence | Evidence Artifact/Anchor resolver and CAS | digest, selector, provenance, and multimodal fixtures |
| execution | Work Item/Attempt lease and HostEvent ingestion | duplicate, unknown, retry, and provider-failure fixtures |
| policy | local AdaptiveResearchPolicy | baseline-zero, growth, pruning, contradiction, and method-switch traces |
| interaction | alignment planner and handoff/acceptance contracts | one-prompt, stale-confirmation, disagreement, and feedback runs |
| delivery | semantic compilers and report manifest | claim-to-source, implementation boundary, depth, and acceptance gates |
| operations | migration, CLI, setup, trace, and audit export | clean-checkout, install, rollback, and replay evidence |

No capability is considered delivered if its proof is only a unit test for a helper while the end-to-end contract remains unexercised.

### 15. Failure semantics are part of the public API

Expected failures use stable machine-readable codes and a common shape containing `code`, `category`, `retryability`, `run_id`, `attempt_id` when applicable, `unmet_obligations`, `safe_message`, `evidence_refs`, and `next_action`. The registry distinguishes invalid input, stale revision, permission denial, unavailable provider, unknown attempt, failed oracle, unresolved evidence, contradiction, migration collision, canonical-store outage, and terminal authority block.

Every failure path has an explicit state effect, retry policy, escalation owner, and audit event. A textual blocked message without persisted cause and recovery action is not a valid outcome.

### 16. Delivery is an independently verifiable vertical slice

Implementation proceeds in slices that each cross storage, coordinator, adapter, CLI, tests, and documentation. A slice is accepted only when a clean-checkout command can create a run, execute a real or fixture event trace, recover it, explain it, produce both reports, and export an audit manifest. This prevents the project from accumulating isolated schemas that never compose into a usable skill.

### 17. The initial persistence layout is fixed for alpha2

Alpha2 uses one workspace-scoped database at .research-tree/run-ledger.sqlite3 with schema migrations recorded in schema_migrations. The database is the authority for all runs in that workspace; round_id remains a compatibility alias mapped to run_id plus a lineage revision. The CAS root is .research-tree/cas/sha256/<first-two>/<digest>. Temporary staging is .research-tree/staging/; rebuildable projections are .research-tree/projections/; retained redacted evaluation results are evaluation/results/; raw and disposable evaluation runs stay under ignored .research-tree/evaluation-runs/.

SQLite schema v1 includes runs, artifacts, artifact_parents, events, attempts, leases, evidence, oracles, closures, insights, host_events, deliveries, acceptances, migrations, and audit_exports, with foreign keys, unique (run_id, event_id), unique content digests, and expected-revision optimistic concurrency. CAS writes are staged, fsynced, digest-checked, and linked in the same coordinator operation; orphan blobs are quarantined for GC and never treated as evidence.

Field-level legacy mapping is fixed in registries/legacy-field-map-v1.json. In particular, round_id is an alias rather than a second key, old tree and host status values are observations to be translated, and validation_result.status and human-brief cannot write canonical closure or acceptance.

### 18. Policy formulas and calibration are deterministic

The policy stores a feature vector in the order evidence_class, independence, contradiction, oracle, implementation_uncertainty, and decision_closure, each normalized to [0,1]. Default weights are [0.18, 0.14, 0.18, 0.20, 0.12, 0.18] and are versioned in the policy registry. Expected action value is:

E = criticality * dot(weights, predicted_delta) * method_fit - depth_penalty - duplicate_penalty - stagnation_penalty.

For outcome proportions p_j, gain-ratio normalization uses GR = gain / max(epsilon, -sum(p_j * log2(p_j))), with epsilon 1e-9. After a verified oracle failure, boosting reweights the affected feature by 1 + failure_boost and renormalizes; the failure boost, seed, and calibration corpus are recorded. Pessimistic pruning defers an optional branch when its lower confidence bound is no better than the retained sibling, while mandatory P0, contradiction, counterevidence, and validation branches bypass score-only pruning.

The policy is deterministic for a fixed ledger digest, registry version, configuration, and seed. Tie-breaking is descending criticality, descending expected value, ascending depth, then lexical action id. Score thresholds propose work; only closure, readiness, evaluation, and acceptance gates can stop a run.

### 19. Host capability differences are negotiated, not guessed

Each adapter publishes a capability matrix for open-text questions, native ask tools, delegation, parallel workers, background execution, network/search, restart hooks, filesystem writes, and structured event transport. The coordinator selects a host execution plan from that matrix and records unsupported capabilities with fallback behavior. A host cannot claim parity by merely producing a Markdown report.

### 20. The evaluation and repository namespaces are fixed before implementation

evaluation/ is the sole tracked evaluation source namespace. Its registered subtrees are cases/, schemas/, harness/, baselines/, results/, and reviews/. Disposable transcripts and raw runs are written only to ignored .research-tree/evaluation-runs/. The empty evals/ root is retired with a migration note. The path registry, documentation registry, and generated-package provenance manifest are checked in before runtime cutover.

### 21. Registries are executable release inputs

The checked-in registries under `registries/` are not illustrative notes. The
lifecycle matrix, error catalog, host capability matrix, task execution registry,
delivery coverage matrix, documentation authority registry, evaluation path registry,
repository path registry, and legacy field map are loaded by contract validation.
Each registry has a version, owner, digest in the release manifest, and an explicit
unknown-entry behavior. A missing registry entry is a release-blocking error; a host
capability marked `host-dependent` is treated as unsupported until an adapter probe
records a result and fallback.

### 22. Corrections are transactional invalidation events

A material requester correction enters the coordinator as a canonical
FeedbackEvent, not as free-form prose appended to the current brief. The event
records the contradicted artifact refs, affected outcome/scope/authority/success
fields, impact class, task-identity disposition, and expected run revision. In
one transaction the coordinator preserves the prior state, appends the
successor interpretation, marks dependent actions and derived artifacts stale,
and emits the next permissible action.

Invalidation follows explicit dependency edges. A corrected premise can stale
the strategy digest, handoff, work items, closure tokens, Insight Digest,
readiness, deliveries, and acceptance, but it never deletes the prior evidence
or attempt. Running work is cancelled, quarantined, or allowed to finish only
as historical evidence; it cannot satisfy the successor state without fresh
review. A repository or product mentioned during diagnosis remains an evidence
subject unless the current Context Pack explicitly selects it as the task
target.

Alternative considered: let the model rewrite the Living Brief and continue.
This was rejected because the black-box transcript shows that prose
acknowledgement does not prevent stale-plan execution or task contamination.

### 23. Attribution is an evaluator-owned experiment

Runtime traces record host and model identity as context but do not infer why a
behavior occurred. The evaluation harness owns causal-attribution experiments.
It registers a comparison key, fixed brief and Context Pack digests, skill and
tool manifests, authority and environment digests, success oracle, and the one
factor allowed to vary. A run pair that changes additional factors is
non-controlled context, not causal evidence.

The Claude Code and GLM5.2 conversation becomes a versioned regression fixture
for observed state-transition failures. It does not become evidence that
GLM5.2 caused them. When a required comparison runtime is unavailable, the
result remains `unavailable` and the cause remains `unresolved`.

Alternative considered: permit cautious model-specific language from a single
trace. This was rejected because hedging does not repair the missing comparison
and can still harden an unsupported hypothesis into product policy.

## Risks / Trade-offs

- **[Migration rejects previously "complete" runs]** -> Import legacy artifacts with explicit `legacy_unverified` dispositions and require alpha2 closure/readiness before completion.
- **[SQLite single-writer contention]** -> Keep transactions short, make the coordinator the only canonical writer, use WAL for readers, and persist worker output outside the transaction before ingestion.
- **[Evidence resolution cannot prove truth]** -> Separate provenance/integrity from semantic confidence, require counterevidence and risk-tiered oracles, and expose residual uncertainty.
- **[Automated semantic evaluation can be gamed]** -> Use deterministic invariants first, then hidden implementation oracles and blinded expert review; an LLM judge is never sole authority.
- **[Host capabilities differ]** -> Version the event contract and test semantic parity while allowing host-specific dispatch and UI behavior.
- **[Long-horizon research can stall]** -> Persist attempts, no-change penalties, method-switch actions, leases, and resumable checkpoints; operational limits pause rather than complete.
- **[Removing old paths is disruptive]** -> Stage import, read-only compatibility projections, shadow evaluation, and explicit cutover; never use permanent dual writes.
- **[Human acceptance can delay terminal completion]** -> Separate research/readiness completion from final delivery acceptance while keeping the overall run non-complete and resumable.
- **[Governance work expands the alpha2 critical path]** -> Treat documentation, evaluation assets, and path boundaries as release integrity work; sequence inventories early and avoid unrelated content rewrites.
- **[Directory migration can overwrite local evidence]** -> Inventory and classify first, never automatically delete untracked paths, and require an explicit migration map with collision checks.
- **[Historical documents can be mistaken for current requirements]** -> Preserve them with supersession metadata and exclude them from active-contract validation unless explicitly referenced.
- **[A large contract remains unimplemented behind green schema checks]** -> Require a vertical-slice smoke path and requirement-to-evidence matrix before each capability is marked complete.
- **[New API names diverge from existing services]** -> Define compatibility aliases and an explicit deprecation/removal matrix before changing public entry points.

## Migration Plan

1. Freeze alpha1 at tag `0.0.1-a1` and land adversarial semantic regression fixtures.
2. Ratify the contract registry, capability specs, transition matrix, error catalog, and ADRs; introduce the storage protocol, SQLite RunLedger, CAS, and idempotent legacy importer without changing current reads.
3. Add canonical entity validators and examples for Evidence Artifact, OracleRun, SlotClosureAssessment, Work Item, Attempt, HostEvent, DeliveryAcceptance, and release manifests.
4. Add Evidence Artifact, OracleRun, and SlotClosureAssessment implementations and migrate canonical Finding Pack ingestion.
5. Introduce ResearchRunCoordinator behind an alpha2 feature boundary and route the structured Decision Ledger/Readiness/Delivery path through it.
6. Demote recursive search to AdaptiveResearchPolicy and remove its closure/delivery authority.
7. Convert Codex and Claude Code adapters, then Hermes, to Host Event Protocol translators. Keep legacy state read-only for comparison.
8. Replace fixed alignment planning, adapter report gates, and Human Brief naming; add revision-bound acceptance and the one-prompt interaction contract.
9. Ratify the documentation authority registry, repository path registry, evaluation asset taxonomy, and host capability matrix; inventory current tracked and untracked classes without deleting user artifacts.
10. Migrate documentation and evaluation definitions, enforce generated-package provenance, and establish governed locations for retained baselines, expert reviews, and redacted run evidence.
11. Expose the stable coordinator CLI/API, migration commands, trace/replay commands, setup smoke checks, and a clean-checkout vertical-slice command.
12. Run cross-host shadow and black-box evaluation against alpha1 from a clean checkout. Fix all false-completion, parity, asset-provenance, layout, and contract violations.
13. Cut over package builds and setup documentation. Stop writing legacy state paths and mark unsupported schema versions explicitly.
14. Remove compatibility projections only after migration, rollback, vertical-slice, and release-manifest checks pass.

Rollback before cutover restores alpha1 readers against untouched legacy inputs. Rollback after cutover restores the prior application version while retaining the append-only alpha2 database; alpha2 writes are never back-projected as trusted alpha1 closure.

## Open Questions

- Exact host event transport may be CLI, library call, or hook callback per platform, provided all variants satisfy the fixed persisted envelope and capability matrix.
- Human acceptance UI remains host-specific; the canonical acceptance artifact, displayed digest, and contextual confirmation rules are host-neutral.
- Risk-tier calibration may adjust the pre-registered defaults after the first corpus pilot, but a candidate cannot change thresholds after seeing scored results.
