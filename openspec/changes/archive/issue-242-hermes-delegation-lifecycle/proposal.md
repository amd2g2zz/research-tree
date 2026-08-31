## Why

The Hermes delegation surface is real and proven: the official
`nousresearch/hermes-agent` image runs, `delegate_task(tasks=[...])` executes
real parallel children, and the supported synchronous one-shot channel
(`hermes -t delegation -z`) aggregates a two-child batch to completion. But no
project-mounted bridge binds those real delegation/task/child identities to
the canonical `ResearchRunCoordinator` lifecycle. The current
`scripts/hermes_execution_adapter.py` `record-batch` records caller-supplied
strings as non-authoritative observations only; it never validates identity
binding, Finding Pack admission, or recovery. The previously claimed setup
checkpoint (`e4a28e4`) is unreachable in any repository ref, and the prior
uncommitted hook edits were preserved only as an out-of-repo patch for review.

## What Changes

- Add a real host invocation path for one ready wave through the supported
  synchronous delegation channel, wrapped in a project-mounted bridge that
  records canonical events with actual `delegation_id`/`task_id`/`child_id`.
- Bind each observed child identity to exactly one canonical attempt;
  reject reuse, missing identity, stale attempts, cross-attempt artifacts,
  and caller-invented identities.
- Make `record-batch` fail closed for missing, empty, schema-invalid,
  modified, or cross-attempt Finding Packs instead of echoing caller strings.
- Preserve delegation lifecycle identity in `hermes_runtime_hook.py` via the
  reviewed out-of-repo handoff patch (copy-allowlist intact), covering
  `attempt_id`/`action_id`/`causation_id`/`tool_call_id`/`child_subagent_id`.
- Add pinned run-local dependency installation for AnySearch
  (v2.1.0 rev `6ff6aa958ad9747659d669b5e9984f07c896f2aa`) into
  `HERMES_HOME/skills/anysearch` before Hermes starts: revision/digest
  verification, idempotent install/status, fail closed on drift, no global
  config mutation, no host bind mount.
- Provide interruption recovery: interrupted child attempts marked
  `unknown_outcome`, verified siblings retained, retry as a fresh canonical
  attempt; cancellation and provider failure never become success.
- Capture a live two-child receipt inside the Docker isolation envelope
  (standards §12a) with fault injection and recovery evidence.

## Non-Goals

- No Claude or Codex behavior changes; no cross-host refactors.
- No `hermes chat -q` lifecycle receipt (proven cancellation regression).
- No nested Hermes processes, no synthetic child IDs, no manually authored
  Finding Packs as evidence, no completion from host status alone.
- No Docker sources outside the lane-owned Hermes run envelope; no root
  Dockerfile/Compose.
- No global Hermes config mutation and no bind-mount-only dependency proof.

## Non-Acceptance Conditions

The lane is NOT complete if any of the following is claimed as evidence:

- A capability string, `--version` probe, or image-pull check.
- A synchronous aggregate result without child identity binding (proves only
  that children can complete, not that identities/attempts/artifacts are
  authoritative).
- A passing setup/package suite alone (the prior 45-test pass closed setup
  behavior, not lifecycle/recovery).
- `record-batch` echo of caller-supplied delegation/task/child IDs or paths.
- A one-shot preflight (`hermes -t delegation -z`) without the
  project-mounted bridge recording canonical receipts.
- A receipt from a bare-local run (no Docker envelope) or with a tag-only
  image reference (no resolved digest).
- `unavailable`/`blocked` reported as a pass.

## Non-Regression Constraints (from the blocker ledger)

| Constraint | Source |
|---|---|
| `hermes chat -q` cancels outstanding children on parent shutdown; the supported synchronous channel `hermes -t delegation -z` is the only valid host preflight/execution primitive | Issue #242 probe comments (verified 2026-08-17) |
| The prior adapter-only branch was invalid and superseded; its work re-enters only through reviewed handoff | Coordinator takeover comment |
| The preserved uncommitted hook patch re-enters only after review; the copy-allowlist sanitization rule must remain intact | Task 0 disposition comment (2026-08-18) |
| Live receipts must be Docker-isolated per `docs/development-standards.md` §12a | Development standards |
| Unrelated Windows fsync/SQLite baseline failures must be reported, never masked | Recorded baseline note |
