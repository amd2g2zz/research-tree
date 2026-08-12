## Context

The alpha2 umbrella contract already defines HostEvent, coordinator-owned lifecycle state, durable SourceCapture/AnalysisCheckpoint artifacts, and a declarative host capability registry. Current package adapters can run fixed task attempts, but capability negotiation is not executable, Hermes has a separate observation-only adapter, and no shared NativeWorkflowRun model can prove bounded phases, stale projections, or deterministic recovery.

The implementation must remain dependency-free in installed skill packages. Host APIs are session-owned and cannot be imported or emulated by the runtime, so probes consume explicit observations from the adapter boundary. Native workflow state is a rebuildable projection, not a replacement for SQLite coordinator state.

## Goals / Non-Goals

**Goals:**

- Validate and digest host capability observations before selecting native or fallback execution.
- Project bounded host-specific phases and child attempts from canonical action identities.
- Preserve workflow/script identity across replans and resumes while advancing projection revision.
- Translate workflow lifecycle, failure, cancellation, and reconciliation into canonical HostEvents.
- Make unavailable, partial, denied, failed, and unknown surfaces choose explicit fallbacks.
- Prove native and fallback paths retain identical completion guards and required checkpoint obligations.

**Non-Goals:**

- Calling or emulating proprietary host APIs.
- Moving scheduling, evidence validation, closure, readiness, or completion authority out of the coordinator.
- Implementing research acquisition/search portfolio work owned by #83 or release evaluation work owned by #64.
- Persisting prompts, chain-of-thought, credentials, or raw provider diagnostics.

## Decisions

### Capability observations are explicit and digest-bound

`host_capabilities.py` defines the supported host/capability vocabulary, probe states, required surfaces, and deterministic fallback selection. A probe receives an explicit observation mapping supplied by the host adapter. Registry values such as `host-dependent` remain unsupported until the observation is `available`; partial/denied/failed states are preserved instead of coerced to booleans. The semantic digest binds the host, observation states, selected mode, and fallback.

Alternative considered: environment-variable or executable discovery. Rejected because host task/delegation surfaces are process/session capabilities and executable presence does not prove permission or availability.

### NativeWorkflowRun is a non-authoritative immutable projection

`native_workflows.py` validates workflow, action, phase, child-attempt, permission, capability, strategy, and checkpoint identities. Projection helpers map Claude Code to dynamic phase/agent work, Codex to bounded concurrent ready tasks, and Hermes to batched delegation plus optional goal/Kanban/hook/scheduled-drain mirrors. Every projection declares `completion_authority=coordinator_only`, `authoritative=false`, a maximum phase/child count, and a host-neutral fallback id.

Alternative considered: extend each existing script with unrelated dictionaries. Rejected because cross-host parity and reconciliation need one semantic model and digest.

### Replan and reconciliation preserve identity and quarantine uncertainty

A same-run replan retains `workflow_id` and `script_id`, increments projection revision, marks unfinished phases stale, and appends successor phases bound to the new strategy revision. Resume retains identity and checkpoint refs. Reconciliation compares host observations to the canonical snapshot and classifies children as active, completed, unknown, or stale; cancellation, crash, provider failure, namespace/permission failure, and missing observations remain durable non-success states.

Alternative considered: create a new workflow id on every replan. Rejected because it obscures continuity and makes duplicate/unknown child attempts harder to reconcile.

### Adapters emit HostEvents but never close canonical work

The HostEvent vocabulary gains workflow start, resume, phase completion, checkpoint, provider failure, cancellation/unknown, and reconciliation kinds with field-level payload requirements. Dependency-free scripts call the same shared workflow helpers copied into host packages, or emit schema-equivalent JSON. `complete` and local task-list exhaustion continue to report `complete=false` and `completion_authority=coordinator_only`.

Alternative considered: accept host goal/task completion as a closure signal. Rejected because those surfaces do not verify SourceCapture, AnalysisCheckpoint, evidence, or DeliveryAcceptance.

## Risks / Trade-offs

- **[Host capability observations can lie or become stale]** -> Bind each plan to a capability digest and require reprobe/reconciliation after invocation failure, permission change, or restart.
- **[More event kinds increase protocol compatibility work]** -> Keep schema version 1, add exact required payloads, and test dependency-free authoring/runtime parity.
- **[Installed scripts cannot import the repository package]** -> Keep shared adapter logic dependency-free and include it through the canonical package builder.
- **[Dynamic growth could become unbounded]** -> Require positive `max_phases`/`max_children`, reject projections over either bound, and make each replan consume a new projection revision.
- **[Host observation may disagree with durable state]** -> Classify it as unknown/stale and require a checkpoint-backed retry or coordinator replan; never infer success.

## Migration Plan

1. Add runtime contracts and failing cross-host tests without enabling any native path by default.
2. Extend HostEvent validation and adapters; rebuild generated packages from canonical sources.
3. Enable native projection only when a fresh probe reports all required surfaces available; otherwise retain `coordinator-dispatch-v1`.
4. Record group 26 receipt after focused, full, package, OpenSpec, and governance gates pass.

Rollback disables native selection and keeps prior workflow observations/checkpoints immutable while all work executes through `coordinator-dispatch-v1`.

## Open Questions

None. Exact host API invocation remains an adapter/session responsibility; this change fixes the persisted semantic boundary.
