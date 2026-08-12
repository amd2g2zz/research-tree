## 1. Capability Contracts

- [ ] 1.1 Add failing tests for honest capability states, deterministic digests, invocation failure, and explicit fallback selection.
- [ ] 1.2 Implement the HostCapabilityProbe result, registry validation, manifests, and package-safe probe command.

## 2. Native Workflow Projection

- [ ] 2.1 Add failing tests for bounded NativeWorkflowRun identity, Claude replan continuity, Codex concurrent-ready mapping, and Hermes optional-surface fallback.
- [ ] 2.2 Implement immutable workflow, phase, and child contracts plus host-specific projection/replan/resume helpers.

## 3. Lifecycle And Recovery

- [ ] 3.1 Add failing tests for workflow HostEvent payloads, checkpoint-backed restart, provider/cancellation/permission failures, stale strategy quarantine, and completion rejection.
- [ ] 3.2 Extend runtime and dependency-free HostEvent validation, native adapters, and reconciliation without granting host state authority.

## 4. Packages And Guidance

- [ ] 4.1 Update canonical adapter guidance/manifests and package builder inputs for Claude Code, Codex, and Hermes.
- [ ] 4.2 Rebuild generated host packages and verify package-source parity.

## 5. Verification Evidence

- [ ] 5.1 Run focused and full tests, Ruff, strict local and umbrella OpenSpec validation, package check, governance, and diff checks.
- [ ] 5.2 Bind group 26 task execution, verification receipt, raw output, rollback, and issue evidence to the implementation revision.
