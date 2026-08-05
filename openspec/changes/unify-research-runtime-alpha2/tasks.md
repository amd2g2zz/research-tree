## Task Execution Contract

The checkbox list is a delivery plan, not evidence of implementation. Group metadata
is registered in `registries/task-execution-v1.json`; it is inherited by every task
under that group. A task may be checked only when its dependency groups are verified,
its declared output exists at the registered path, its acceptance command exits zero
in the recorded environment, its focused and regression evidence is linked, and its
rollback action is documented. The implementation release must additionally emit a
generated requirement matrix from `registries/delivery-matrix-v1.json`; every
`### Requirement` and `#### Scenario` is required to have one unique row and one
resolvable evidence reference. GitHub issue closure is tracking metadata, never a
substitute for local evidence.

## 1. Contract and Alpha1 Baseline (#55, #66)

- [ ] 1.1 Add an alpha1 fixture manifest that pins tag `0.0.1-a1`, exact environment inputs, host package revisions, commands, and expected unsafe outcomes. Implementation evidence: `evaluation/cases/alpha1-adversarial-v1.json` and evaluator-owned oracle map; group acceptance remains pending until the complete baseline suite is recorded.
- [ ] 1.2 Convert forged validation status, missing evidence reference, filler report, empty frontier, and adapter-only completion into negative semantic regression tests.
- [ ] 1.3 Add alignment fixtures for premature handoff, active disagreement, generic acknowledgement, and repeated unconsumed reconnaissance.
- [ ] 1.4 Add provider-failure, stale event, duplicate event, and crash-boundary fixtures for native and Hermes paths.
- [ ] 1.5 Register hidden-oracle boundaries so worker-visible fixtures cannot access eventual patches or expected answers. Implementation evidence: public cases carry oracle IDs only; outcomes remain in `evaluation/harness/alpha1_adversarial.py`.
- [ ] 1.6 Link each fixture and acceptance oracle back to the corresponding alpha2 capability requirement and GitHub issue.

## 2. SQLite RunLedger and Content-Addressed Storage (#53)

- [ ] 2.1 Introduce a storage protocol that preserves the existing ArtifactRevision, parent-reference, round, and event operations without coupling domain services to filesystem paths.
- [ ] 2.2 Define and migrate SQLite schema version 1 for runs, artifact revisions, artifact parents, events, action attempts, evidence metadata, oracle runs, and host events.
- [ ] 2.3 Configure foreign keys, WAL, full synchronization, busy timeout, short transactions, and expected-revision conflict handling on every connection.
- [ ] 2.4 Implement immutable artifact append, exact revision resolution, round reconstruction, event append, and lineage integrity checks in the SQLite backend.
- [ ] 2.5 Implement the SHA-256 content-addressed store with atomic writes, digest verification, media metadata, and workspace-boundary enforcement.
- [ ] 2.6 Add concurrency, stale-write, dangling-parent, tamper, restart, and deterministic-replay tests for SQLite and the CAS.
- [ ] 2.7 Add an idempotent importer for filesystem RunStore rounds and verify repeated import produces no duplicate revisions or events.

## 3. Resolvable Evidence Artifacts (#54)

- [ ] 3.1 Define EvidenceArtifact and EvidenceAnchor schemas for source snapshots, repositories, input-ledger entries, experiments, documents, and images.
- [ ] 3.2 Implement selector validation for repository revision/path/symbol/line, source fragment, document page/section, image region, input revision, and experiment result field.
- [ ] 3.3 Add evidence acquisition metadata, applicability, confidence, limitations, provenance origin, and independence-group normalization.
- [ ] 3.4 Implement resolvers that verify exact artifact revisions, content digests, workspace scope, and source/repository baseline compatibility.
- [ ] 3.5 Update FindingPackCompiler to accept only resolvable evidence anchors for consequential observations and to persist exact parent lineage.
- [ ] 3.6 Add tests for missing, changed, out-of-scope, derivative, multimodal, and repository-revision evidence.

## 4. OracleRun and Slot Closure (#56)

- [ ] 4.1 Define OracleSpec, OracleAttempt, OracleRun, and SlotClosureAssessment schemas with exact revision and attempt binding. Partial implementation evidence: strict `OracleSpec`, `OracleRun`, and `SlotClosureAssessment` contract parsers; persisted OracleAttempt binding remains open.
- [ ] 4.2 Implement oracle result ingestion for method, environment, inputs, tool events, result artifacts, evaluator, verdict, and limitations. Partial implementation evidence: `OracleRun.from_mapping` validates the canonical result boundary and `ResearchRunCoordinator.record_oracle_run` persists exact attempt-bound results while resolving tool-event refs; result-artifact resolution remains open.
- [ ] 4.3 Remove authoritative meaning from worker-authored validation status strings and migrate Finding Packs to OracleRun references. Partial implementation evidence: coordinator rejects arbitrary P0 closure obligations and only accepts persisted core tokens; Finding Pack legacy validation field migration remains open.
- [ ] 4.4 Implement closure checks for evidence classes, provenance independence, counterevidence, contradictions, oracle status, selected or conditional decision, fallback, and reversal condition. Partial implementation evidence: `SlotClosureAssessment.assess_alpha2` binds an exact persisted Decision Ledger revision and selected/conditional status; multi-slot aggregation remains open.
- [ ] 4.5 Make the core evaluator the only closure-token issuer and persist machine-readable pass, fail, and inconclusive explanations. Partial implementation evidence: deterministic token/revocation, coordinator-owned SQLite persistence, and append-only revocation after material feedback; direct parent-supersession triggers remain open.
- [ ] 4.6 Generate independent validation, method-switch, fallback, or residual-risk work after failed or inconclusive oracles. Partial implementation evidence: `oracle_successor_actions`; scheduler integration remains open.
- [ ] 4.7 Pass adversarial tests for nonexistent references, forged verdicts, active contradictions, and manual close-slot bypass attempts.

## 5. Single-Authority ResearchRunCoordinator (#57)

- [ ] 5.1 Define the canonical lifecycle states and allowed transitions from alignment through autonomous research, synthesis, readiness, delivery, acceptance, completion, supersession, and authority blocking.
- [ ] 5.2 Implement coordinator initialization from an explicitly confirmed alignment artifact and exact Blueprint Target lineage.
- [ ] 5.3 Implement transactional action dispatch, attempt leasing, Finding Pack ingestion, insight synthesis, decision convergence, readiness, and successor-work transitions.
- [ ] 5.4 Implement completion as the conjunction of P0 closure tokens, non-blocking insight state, readiness, required evaluation, both deliveries, and revision-bound user acceptance.
- [ ] 5.5 Reject host, worker, hook, report-file, empty-frontier, and completed-wave completion attempts with persisted reasons.
- [ ] 5.6 Implement supersession and same-round replanning rules without mutating prior round artifacts.
- [ ] 5.7 Add coordinator recovery tests at every transition boundary and prove repeated event ingestion is idempotent.
- [ ] 5.8 Add an authority-bypass audit that proves recursive_search.py, native_execution_adapter.py, Hermes adapters, and hooks cannot set canonical completion from local status, report size, heading count, or worker count.

## 6. Local AdaptiveResearchPolicy (#58)

- [ ] 6.1 Rename recursive search concepts and expose a pure AdaptiveResearchPolicy that consumes canonical Decision Slot deficits and emits typed action proposals.
- [ ] 6.2 Remove canonical Slot status, report manifest, delivery registration, and run-completion authority from the recursive-search projection.
- [ ] 6.3 Implement landscape, deep-dive, adversarial, validation, and method-switch proposals with triggering evidence, missing evidence, method boundary, and closure oracle.
- [ ] 6.4 Replace the scalar-only evidence delta with auditable closure components for evidence class, independence, contradiction, oracle, implementation uncertainty, and Slot closure.
- [ ] 6.5 Implement gain-ratio branch normalization, duplicate/dominated optional pruning, no-change penalties, and oracle-failure reweighting.
- [ ] 6.6 Exempt P0 obligations, counterevidence, unresolved contradictions, and mandatory validation from score-only pruning and frontier capacity.
- [ ] 6.7 Add tests for baseline delta zero, evidence-triggered growth, correction growth, unbounded worker suggestions, repeated evidence, drained frontier, and method switching.

## 7. Evidence-Bearing Mutual Alignment (#59)

- [ ] 7.1 Extend alignment persistence with action attempts, pending-action identity, belief basis, confidence, disagreement disposition, and supersession lineage.
- [ ] 7.2 Implement candidate scoring for reconnaissance, one open question, constructive disagreement, and confirmation using recorded semantic factors.
- [ ] 7.3 Ensure agent-verifiable ambiguity consumes a reconnaissance attempt before requesting the technical fact from the user when reconnaissance has expected value.
- [ ] 7.4 Implement candidate-understanding repair and supported/refuted/not-enough-information disagreement handling without overwriting either participant's belief.
- [ ] 7.5 Enforce one short open prompt per user turn while preserving unresolved internal gaps across turns.
- [ ] 7.6 Require semantic readiness, displayed digest freshness, and contextual user confirmation before autonomous handoff.
- [ ] 7.7 Route material post-handoff target, priority, authority, or success changes through feedback lineage and successor-round creation.
- [ ] 7.8 Add black-box alignment tests for vague briefs, impossible goals, wrong human premises, wrong agent premises, repeated planning, and generic acknowledgement.

## 8. Host Event Protocol and Native Adapters (#60)

- [ ] 8.1 Define the versioned HostEvent envelope and validators for dispatch, attempt, submission, review, provider failure, unknown outcome, retry, and worker completion.
- [ ] 8.2 Implement expected-revision, attempt-binding, duplicate-event, stale-event, and unsupported-version handling in the coordinator ingestion boundary.
- [ ] 8.3 Refactor the Codex adapter to dispatch native subagents and submit HostEvents without maintaining closure, readiness, report, or completion state.
- [ ] 8.4 Refactor the Claude Code adapter independently for its package format and native tools while using the same HostEvent contract.
- [ ] 8.5 Preserve open conversational alignment when a native question tool cannot express an unconstrained prompt.
- [ ] 8.6 Add source-checkout, installed-package, Windows, POSIX, rebuild, and package-parity tests for both native adapters.
- [ ] 8.7 Prove equivalent Codex and Claude event fixtures produce the same canonical semantic digest.
- [ ] 8.8 Define activation evidence states for discovery, current installation, live body injection, and post-activation behavior; require explicit host receipts instead of inferring activation from a file read.
- [ ] 8.9 Add host-specific activation markers, side-effect-free probes, package digests, and bounded receipts for Codex, Claude Code, and Hermes.
- [ ] 8.10 Add stale-link classification and non-destructive refresh handling to setup/status, including the legacy repository-root path failure mode.
- [ ] 8.11 Run native activation probes in isolated Codex, Claude Code, and Hermes fixtures; mark unavailable CLIs as unavailable evidence and retain exact outputs.

## 9. Hermes-Native Long-Horizon Adapter (#61)

- [ ] 9.1 Map Hermes delegation, goals, Kanban tasks, and lifecycle outcomes to HostEvents without duplicating business state.
- [ ] 9.2 Project action evidence standards and closure oracles into Hermes goal acceptance criteria while retaining core verification authority.
- [ ] 9.3 Normalize provider/model identity, retry category, opaque error code, attempt identity, and safe gateway-log reference without persisting raw provider details.
- [ ] 9.4 Implement retry, alternate provider, method switch, unknown-attempt recovery, and post-restart reconciliation within confirmed authority.
- [ ] 9.5 Treat hooks as fail-open observability and wake-up signals and test that hook failure cannot bypass evidence or completion gates.
- [ ] 9.6 Build Hermes-specific package and setup checks without copying Codex or Claude package structure.
- [ ] 9.7 Run a long-horizon provider-failure fixture through restart and prove semantic parity with the native-host outcome.

## 10. Semantic Dual Delivery and Acceptance (#62)

- [ ] 10.1 Rename the canonical human-facing artifact and public contract from Human Brief to Human Research Report with an explicit legacy compatibility disposition.
- [ ] 10.2 Remove adapter Markdown byte/heading verification and route all delivery creation through DeliveryCompiler and exact Decision Ledger lineage.
- [ ] 10.3 Extend the Technical Research Package contract for applicable architecture, interfaces, state flows, permissions, implementation order, repository touchpoints, validation, observability, migration, rollout, and rollback.
- [ ] 10.4 Extend the Human Research Report contract for evidence-backed reasoning, alternatives, trade-offs, expected capability, applicability, risks, uncertainties, and implementation meaning.
- [ ] 10.5 Add semantic readiness diagnostics for orphan claims, missing implementation boundaries, unresolved P0 conditions, and shallow human reasoning.
- [ ] 10.6 Define DeliveryAcceptance bound to exact technical and human artifact revisions and reject generic acknowledgement.
- [ ] 10.7 Route rejection for intent or depth into same-round evidence work or a traceable successor round.
- [ ] 10.8 Add filler-report, orphan-claim, stale-acceptance, legacy-Human-Brief, and independent-implementation tests.

## 11. Causal Observability and Recovery Tools (#63)

- [ ] 11.1 Define redacted causal trace events for lifecycle, action selection, evidence validation, growth, pruning, oracle, retry, readiness, delivery, and acceptance.
- [ ] 11.2 Implement `explain-run` and `why-action` projections with inputs, score components, selected action, rejected alternatives, and evidence references.
- [ ] 11.3 Implement `why-not-complete` with every unmet canonical obligation and its next permissible action.
- [ ] 11.4 Implement deterministic `replay` and semantic state-digest comparison from immutable ledger records.
- [ ] 11.5 Implement `reconcile-host` for missing, duplicate, stale, divergent, and uncertain host outcomes.
- [ ] 11.6 Add redaction tests that exclude secrets, credentials, full prompts, private reasoning, and raw provider diagnostics while preserving safe diagnostic fields.
- [ ] 11.7 Replace timestamp-only trace recency ordering with canonical sequence and causation ordering; add a clock-regression fixture that proves the newest emitted event remains newest in summaries and replay.

## 12. Cross-Host Black-Box Evaluation (#64)

- [ ] 12.1 Version cases for vague intent, wrong human premise, wrong agent premise, infeasible goal, repository research, conflicting sources, multimodal input, recursive discovery, unavailable tools, provider failure, crash recovery, and material feedback.
- [ ] 12.2 Add hidden fact and implementation oracles that remain outside worker-visible requests and pin source permission, baseline revision, and environment digest.
- [ ] 12.3 Extend BlueprintEvaluationSuite with intent fidelity, premature handoff, unsupported claim, P0 coverage, contradiction, oracle reproducibility, false completion, recovery, host parity, rediscovery burden, and acceptance metrics.
- [ ] 12.4 Run isolated implementation attempts against exact alpha2 packages, alpha1 packages, and a registered simpler-prompt baseline.
- [ ] 12.5 Add blinded expert review for problem fidelity, evidence quality, professional depth, technical correctness, and implementation usefulness.
- [ ] 12.6 Persist raw case artifacts, commands, results, comparisons, limitations, and component diagnoses for audit.
- [ ] 12.7 Enforce zero false completion, fully resolvable P0 evidence/closure, recovery, and cross-host parity as non-negotiable release gates.
- [ ] 12.8 Publish an alpha2 evaluation report that states improvements, regressions, residual uncertainty, and unsupported claims without proxy-based self-congratulation.

## 13. Migration, Packaging, and Cutover (#65)

- [ ] 13.1 Inventory alpha1 filesystem RunStore, alignment SQLite, native checkpoint, Hermes checkpoint, Finding Pack, report, and package schema variants.
- [ ] 13.2 Implement idempotent import dispositions for legacy evidence, validation, closure, completion, Technical Research Package, and Human Brief artifacts.
- [ ] 13.3 Add read-only compatibility projections for shadow comparison without dual-writing canonical completion state.
- [ ] 13.4 Update canonical build sources and generate separate Codex, Claude Code, and Hermes packages with host-specific manifests, references, scripts, and setup instructions.
- [ ] 13.5 Add package hash/parity, stale-package, strict UTF-8 without BOM, runtime discoverability, and source/install launch tests.
- [ ] 13.6 Run upgrade and rollback drills and verify alpha2 artifacts are never back-projected as trusted alpha1 closure.
- [ ] 13.7 Stop writing `.research-tree-native` and `.research-tree-hermes` completion state only after all black-box release gates pass.
- [ ] 13.8 Document unsupported schema behavior, recovery, migration, rollback, and final legacy-path removal.

## 14. Canonical Schemas and Lifecycle Contract (#53, #56, #57, #60)

- [ ] 14.1 Create schemas/ with versioned JSON schemas, valid/invalid examples, owner metadata, and migration notes for every canonical entity.
- [ ] 14.2 Define the exact InputRecord, PermissionProfile, AlignmentMessage, FeedbackEvent, ResearchRun, DecisionSlot, ResearchAction, WorkItem, AttemptLease, EvidenceArtifact, EvidenceAnchor, OracleSpec, OracleRun, SlotClosureAssessment, InsightDigest, ReadinessRecord, HostEvent, DeliveryManifest, DeliveryAcceptance, and ReleaseManifest fields.
- [ ] 14.3 Publish the schema, protocol, package, template, and database compatibility matrix with reader/writer support, lossless migrators, deprecation, and rejection rules.
- [ ] 14.4 Implement shared validators and contract-test generation so runtime ingestion and host emission use the same schemas.
- [ ] 14.5 Publish the lifecycle matrix for alignment, handoff_pending, autonomous_research, synthesis, readiness, delivery_pending, awaiting_acceptance, completed, paused, blocked, superseded, authority_blocked, and failed.
- [ ] 14.6 Define pause, resume, cancel, provider outage, safety violation, infeasible objective, acceptance rejection, and supersession transitions with guards, side effects, actors, and stable errors.
- [ ] 14.7 Add replay tests for illegal, stale, duplicate, out-of-order, and terminal transitions and verify identical semantic digests on Windows and POSIX.

## 15. Worker Orchestration and Acquisition (#54, #56, #58, #60, #61)

- [ ] 15.1 Define worker assignment, attempt, lease, heartbeat, cancellation, and retry schemas with role, objective, tools, permissions, inputs, output contract, oracle, timeout, and owner.
- [ ] 15.2 Implement lease renewal, heartbeat timeout, unknown-attempt recovery, retry identity, exponential backoff, alternate-provider selection, and human escalation rules.
- [ ] 15.3 Define fan-out/fan-in independence groups, method identity, review quorum, duplicate provenance, disagreement handling, and partial-submission dispositions.
- [ ] 15.4 Add typed empty, malformed, partial, provider-failed, and cancelled Finding Pack handling with persisted next actions.
- [ ] 15.5 Create the method/tool registry for repository, web/search, document, image, experiment, and code-execution methods with capability, permission, timeout, retry, provenance, and limitation metadata.
- [ ] 15.6 Implement immutable source snapshots, URL response digests, derivative provenance groups, license/access records, parser versions, and multimodal selector resolvers.
- [ ] 15.7 Add acquisition fallback tests for no-result search, blocked URLs, parser errors, unsupported media, rate limits, unavailable tools, and changed source digests.
- [ ] 15.8 Add scheduler-tick/no-progress traces and prove method switch or authority blocking when a P0 obligation survives the registered no-change threshold.

## 16. Insight Synthesis and Policy Calibration (#58, #59)

- [ ] 16.1 Define and validate the InsightDigest schema, producer version, source revisions, fact/inference/recommendation/unknown classes, contradiction sets, gaps, confidence, and limitations.
- [ ] 16.2 Implement deterministic digest recomputation, supersession lineage, changed-field detection, and invalidation of dependent closure/readiness/delivery artifacts.
- [ ] 16.3 Specify and persist the evidence-delta feature vector, default weights, method-fit model, gain-ratio epsilon, pruning confidence rule, boosting update, seed, and calibration corpus.
- [ ] 16.4 Implement deterministic tie-breaking and score audit records; keep score thresholds advisory and closure/readiness/evaluation/acceptance as terminal gates.
- [ ] 16.5 Add fixtures for baseline delta zero, duplicate evidence, contradiction, invalid premise, failed oracle, method limitation, branch dominance, P0 pruning exemption, and no-progress recovery.

## 17. Security and Execution Boundary (#53, #54, #56, #60, #61)

- [ ] 17.1 Define safety tiers and permission profiles for read roots, write roots, executables, network endpoints, environment variables, secrets, timeouts, and output destinations.
- [ ] 17.2 Implement path, symlink/junction, archive, parser, network, and oracle sandbox checks with stable policy-violation events.
- [ ] 17.3 Implement secret, private-prompt, hidden-oracle, and raw-provider redaction for findings, traces, reports, evaluation results, and release manifests.
- [ ] 17.4 Record license/access and redistribution policy for external sources and block non-reproducible public fixtures without an explicit limitation.
- [ ] 17.5 Add adversarial execution fixtures for path escape, undeclared command/network, credential leakage, hidden-oracle leakage, and unsafe output destination.

## 18. Implementation Vertical Slices and Release Evidence (#53-#70)

- [ ] 18.1 Create a machine-readable requirement-to-delivery matrix mapping every requirement to source owner, public surface, migration impact, focused tests, black-box case, evidence artifact, and GitHub issue. Implementation present; dependency and release evidence remain pending.
- [ ] 18.2 Define public Python API, CLI JSON schemas, configuration precedence, supported Python/OS matrix, package manifests, and first-success smoke commands for all three hosts.
- [ ] 18.10 Define the source-checkout launcher contract so documented test and subprocess commands resolve research_tree without an accidental PYTHONPATH dependency; test both direct interpreter and uv-managed invocation. Implementation evidence: `scripts/run_research_tree.py`, `tests/test_runtime_discoverability.py::test_source_checkout_launcher_works_without_pythonpath`, and `uv run pytest -q tests/test_runtime_discoverability.py`; group dependencies remain pending.
- [ ] 18.3 Implement migration inventory, dry-run, apply, verify, rollback, and status commands with source digests, collision reports, operator confirmations, and non-destructive untracked-data handling.
- [ ] 18.4 Define and emit an immutable release manifest containing source revision, host package hashes, schema versions, test/evaluation commands, baselines, environments, verifier identity, limitations, and gate results.
- [ ] 18.5 Freeze evaluation cases, baselines, metric aggregation, missing-data handling, expert rubric, and thresholds before candidate runs and reject post-hoc changes.
- [ ] 18.6 Add a Definition-of-Done checker that rejects tasks lacking code, focused tests, regression results, documentation, migration notes, and linked evidence where required.
- [ ] 18.7 Add feature flags, compatibility aliases, observation-window metrics, rollback triggers, and final legacy-authority removal checks.
- [ ] 18.8 Run the complete vertical slice on clean Windows and POSIX checkouts and retain command output and manifest as release evidence.
- [ ] 18.9 Export an offline-verifiable evidence bundle that resolves every release claim to case, command, environment, artifact, oracle, trace, comparison, and limitation.

## 19. Documentation Governance (#68)

- [ ] 19.1 Inventory README, PRODUCT, OpenSpec, ADRs, legacy RT specifications, shared references, generated package documents, operational notes, and evaluation reports.
- [ ] 19.2 Define and publish the documentation authority registry with class, canonical source, audience, owner, lifecycle, update trigger, supersession rule, and validation rule.
- [ ] 19.3 Ratify the authority relationship among PRODUCT, OpenSpec, ADRs, README, historical RT specifications, and generated host packages.
- [ ] 19.4 Add explicit historical/superseded metadata and resolvable successor links without deleting decision history.
- [ ] 19.5 Add generated-document provenance, stale-copy, terminology, index-membership, and internal-link checks.
- [ ] 19.6 Align active documentation with Human Research Report and the alpha2 runtime while permitting annotated legacy compatibility references.
- [ ] 19.7 Update README and contributor entry points to expose the enforced documentation and evaluation governance model.

## 20. Evaluation Asset Governance (#69)

- [ ] 20.1 Inventory `evaluation/`, `evals/`, experience reports, session JSONL, raw evidence, case manifests, evaluator code, hidden-oracle interfaces, and release outputs by lifecycle class.
- [ ] 20.2 Ratify one canonical evaluation namespace and a non-overlapping directory contract for cases, schemas, harnesses, fixtures, baselines, results, reviews, transcripts, and disposable output.
- [ ] 20.3 Define tracked/ignored policy, provenance schema, retention, redaction, size limits, stable identifiers, and safe hidden-oracle references.
- [ ] 20.4 Migrate or explicitly retire the ambiguous `evals/` root and preserve compatibility for `evaluation/cases/v1.json`.
- [ ] 20.5 Classify retained alpha1 experience artifacts and migrate only release-relevant, redacted, provenance-complete evidence.
- [ ] 20.6 Add deterministic evaluation entry points and validators for misplaced output, schema drift, oracle leakage, missing provenance, and oversized transcripts. Implementation present; group dependencies remain pending.
- [ ] 20.7 Update #55 and #64 implementations to consume the governed asset model and reject private local conventions.

## 21. Repository Layout Governance (#70)

- [ ] 21.1 Inventory every top-level path and classify source, generated, installed, runtime, evaluation, build, cache, and historical ownership.
- [ ] 21.2 Define a machine-readable path registry with mutability, tracked status, distribution status, cleanup safety, owner, and canonical command. Implementation present; group dependencies remain pending.
- [ ] 21.3 Reconcile `packages/`, `skill-src/`, shared resources, host overlays, and repository-local `.agents/.claude/.codex` installations with explicit source/generated/install boundaries.
- [ ] 21.4 Reconcile `.gitignore`, package manifests, build/dist output, egg-info, caches, raw material, research runs, and evaluation output with the registry.
- [ ] 21.5 Implement checks for unexpected roots, generated-source drift, host-package leakage, misplaced runtime output, and undocumented artifacts. Implementation present; group dependencies remain pending.
- [ ] 21.6 Prove package build, tests, supported local install, and a sample run leave a clean checkout with no unexplained files.
- [ ] 21.7 Provide a non-destructive migration map with collision detection and explicit confirmation for user-owned untracked artifacts.
- [ ] 21.8 Update repository layout and contributor documentation from the enforced registry.

## 22. Alpha2 Release Completion (#67)

- [ ] 22.1 Run the full unit, integration, adversarial, migration, package, documentation, layout, evaluation-asset, and cross-host black-box suites from a clean checkout.
- [ ] 22.2 Audit every OpenSpec requirement against exact test, runtime artifact, or evaluation evidence and record missing or indirect evidence as incomplete.
- [ ] 22.3 Confirm all P0 GitHub issues #53-#73 are closed with linked implementation and verification evidence.
- [ ] 22.4 Confirm the alpha2 milestone has zero false completion, fully resolvable P0 references, passing recovery/parity, governed evaluation evidence, a clean repository layout, current documentation, improved independent implementation, and accepted expert depth.
- [ ] 22.5 Update release notes, installation and upgrade guidance, known limitations, documentation authority index, repository layout, evaluation entry points, and compatibility matrix for Codex, Claude Code, and Hermes.
- [ ] 22.6 Tag and publish the alpha2 prerelease only after the milestone release definition is proven.

## 23. Transactional Correction Invalidation (#73)

- [ ] 23.1 Write failing unit tests showing `record` rejects a response that does not match the current pending action and agent-only evidence cannot resolve a human-only field. Implementation evidence present; dependencies #53, #57, and #59 remain open.
- [ ] 23.2 Write failing integration tests showing a material FeedbackEvent atomically preserves the prior revision, creates a successor interpretation, and invalidates dependent strategy, handoff, closure, readiness, delivery, and acceptance revisions. Implementation evidence: `tests/test_alpha2_correction_integration.py` and `evaluation/harness/fixtures/correction_invalidation_trace.json`; dependencies remain open.
- [ ] 23.3 Extend the canonical FeedbackEvent and lifecycle contracts with contradicted refs, affected fields, invalidated refs, successor refs, impact class, and task-identity disposition. Implementation evidence: `validate_feedback_event`, `feedback-event-v1.json`, the mutual-alignment correction contract, and `tests/test_alpha2_runtime_contract.py::test_feedback_event_validates_invalidation_lineage_and_terminal_impact`; dependencies remain open.
- [ ] 23.4 Implement correction ingestion and stale-state quarantine through the single ResearchRunCoordinator without adding a second writable authority. Implementation present; dependencies remain open.
- [ ] 23.5 Reject confirmation, dispatch, delivery, and completion commands that reference a digest invalidated by correction, with stable error and next-action fields. Implementation evidence: `ResearchRunCoordinator._assert_current_in_connection`, `tests/test_alpha2_runtime_contract.py::test_material_correction_invalidates_digest_and_keeps_task_identity`, and `uv run pytest -q tests/test_alpha2_runtime_contract.py`; dependencies remain open.
- [ ] 23.6 Add the diagnostic-subject/task-target contamination fixture and prove that old domain strategy cannot survive an explicit requester correction. Implementation present; dependencies remain open.
- [ ] 23.7 Link the implementation, tests, replay trace, and migration disposition to issue #73 and the requirement-to-delivery matrix. Implementation evidence: `registries/delivery-matrix-v1.json` override and `tests/test_delivery_matrix.py`; dependencies remain open.

## 24. Claude Code and GLM5.2 Black-Box Regression (#72)

- [ ] 24.1 Register a redacted case manifest for the reported transcript with exact public turns, expected control transitions, hidden evaluator state, source permission, skill revision, and environment limitations. Implementation present; task-group dependency evidence remains pending.
- [ ] 24.2 Write failing black-box assertions for activation-before-reference, one open prompt, correction invalidation, task identity, recursive continuation, unsupported attribution, and dual-delivery depth.
- [ ] 24.3 Implement the fixture runner and retained evidence paths using the governed evaluation asset model from #69.
- [ ] 24.4 Execute the same registered case against the alpha1 baseline and alpha2 candidate; record non-reproducibility instead of fabricating a baseline failure.
- [ ] 24.5 Execute a controlled Claude Code native versus GLM5.2 comparison when both runtimes are available, otherwise persist an unavailable result with the external blocker.
- [ ] 24.6 Add an attribution validator that rejects model/host causal claims when more than the declared comparison factor changes or comparison evidence is missing. Implementation present; task-group dependency evidence remains pending.
- [ ] 24.7 Link case artifacts, traces, reviewer disposition, and residual uncertainty to issue #72 and the alpha2 release manifest.
