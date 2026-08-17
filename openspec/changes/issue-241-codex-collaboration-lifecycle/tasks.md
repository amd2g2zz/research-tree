# Implementation Tasks

## 1. Spec checkpoint

- [x] Preflight passed at `origin/dev@f95b5e0`; worktree/branch claimed.
- [x] Issue-local OpenSpec written and strict-validated.

## 2. Codex identity binding

- [ ] 2.1 RED: `bind-agent` with `--host codex` and a hook-unobserved
      `agent_id` is rejected (identity must appear in the observed hook
      stream).
- [ ] 2.2 RED: duplicate binding of one Codex child identity to a second
      attempt is rejected; stale attempt mismatch is rejected.
- [ ] 2.3 GREEN: extend `bind_agent` to host `codex` with observed-identity
      admission.

## 3. Hook child-identity extraction

- [ ] 3.1 RED: Codex `SubagentStart` payload with a well-formed agent
      identity records `agent_id` + `binding_status: candidate`; free text
      from the payload is not serialized.
- [ ] 3.2 RED: malformed identity values are dropped, not coerced.
- [ ] 3.3 GREEN: allowlist extraction in `lifecycle_hook.observe` for codex
      SubagentStart/SubagentStop.

## 4. Collaboration translation

- [ ] 4.1 RED: Stop with active attempts emits `unknown_outcome` per active
      attempt (never completion); verified siblings keep their state.
- [ ] 4.2 GREEN: recover/retry path for codex host with fresh attempt IDs.
- [ ] 4.3 REFACTOR: regenerate codex package; parity passes.

## 5. Preserved handoff integration (review-first)

- [ ] 5.1 Apply reviewed portions of `~/rt-241-handoff-20260818.patch`
      (fail-closed bridge + hook enrichment) after re-mapping against
      post-`f95b5e0` sources; discard superseded hunks.

## 6. Gates

- [ ] 6.1 Focused suites green (`tests/test_native_execution_adapter.py`,
      `tests/test_host_event_protocol.py`, `tests/test_lifecycle_hook.py`).
- [ ] 6.2 Full governed suite passes vs the post-#242 baseline.

## 7. Live in-session receipt

- [ ] 7.1 Capability probe refresh: current Codex CLI schema for a
      client-callable collaboration surface; record disposition.
- [ ] 7.2 If bindable: two concurrent tasks in-session with project hooks;
      capture child IDs, Finding Packs, hook sequence, ledger rows,
      fingerprints; Docker envelope or reviewed §12a deviation.
- [ ] 7.3 If still unbindable: blocker receipt on the issue; lane stays
      open; no PR (stop condition).

## 8. Review and delivery

- [ ] 8.1 Independent reviewer replay in a fresh worktree.
- [ ] 8.2 One PR `Closes #241` targeting dev (only if §7.2 succeeded).

## Rollback

`git revert` of the lane's delivery commits on
`feat/issue-241-codex-collaboration`.
