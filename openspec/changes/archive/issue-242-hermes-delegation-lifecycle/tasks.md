# Implementation Tasks

Each task lands as RED → GREEN (one invariant per cycle). Focused test
output is retained under `.research-tree/verification-runs/issue-242/`.

## 1. Spec + baseline (done before source work)

- [x] Task 0 baseline reconciliation comment posted; worktree recreated from
      `origin/dev@43977ed`; preflight passed; full-suite baseline recorded
      (857 passed / 0 failed on this macOS runner; 18 Windows failures not
      reproduced, kept as environment risk).
- [x] Issue-local OpenSpec written and validated strict.

## 2. Hook identity propagation (reviewed handoff patch)

- [x] 2.1 RED: hook records `attempt_id`/`action_id`/`causation_id`/
      `child_subagent_id`→`agent_id`/`tool_call_id`→`causation_id` and env
      fallbacks from a delegate_task payload; free text still dropped.
- [x] 2.2 RED: non-identifier values for `_id` fields are dropped, not
      coerced; 1 MiB bound and event whitelist unchanged.
- [x] 2.3 GREEN: apply reviewed patch to `scripts/hermes_runtime_hook.py`
      keeping copy-allowlist semantics.
- [x] 2.4 REFACTOR: regenerate Hermes package; package parity check passes.

## 3. record-batch fail-closed admission

- [x] 3.1 RED: missing/empty/non-object/modified-digest/cross-attempt
      Finding Pack inputs each exit 1 with a stable message.
- [x] 3.2 RED: caller-supplied delegation/task/child IDs that never appear
      in observed hook events are rejected as unbound identities.
- [x] 3.3 GREEN: validate paths-in-workspace, non-empty object JSON, digest
      match, and attempt ancestry before recording; output remains
      `authoritative: False`.

## 4. Delegation bridge (run-delegation)

- [x] 4.1 RED: a run-delegation request without a coordinator-issued wave
      (schema-1 delegation-wave with attempt/event coordinates) fails
      closed. Cross-wave binding is fail-closed: surplus observations for a
      wave are rejected rather than silently rebound (scope note: persistent
      cross-invocation binding enforcement is the canonical coordinator's
      authority; the adapter rejects mismatches it can observe).
- [x] 4.2 RED: observed child identity binding rejects reuse, missing, and
      cross-attempt identity.
- [x] 4.3 GREEN: the bridge post-processes the observed hook stream for
      one wave and emits validated `build_hermes_event` envelopes
      (attempt_started; worker_finished ONLY on explicitly observed
      `completed` status; unknown_outcome otherwise) for coordinator
      ingestion. The real host invocation of the synchronous channel is
      owned by the blocked live-evidence phase (credential blocker) and is
      NOT claimed here.
- [x] 4.4 RED: interruption mid-batch produces `unknown_outcome` + `retry`
      with a fresh attempt ID (`retry_of` set) while the verified sibling
      stays accepted.
- [x] 4.5 GREEN: recovery path per `recovery_events` contract.

## 5. Pinned dependency setup

- [x] 5.1 RED: dependency manifest declares AnySearch v2.1.0 rev
      `6ff6aa958ad9747659d669b5e9984f07c896f2aa`; missing manifest or
      wrong revision fails closed.
- [x] 5.2 RED: install into run-local `HERMES_HOME/skills/anysearch` is
      idempotent; status reports revision/digest; drift fails closed.
- [x] 5.3 GREEN: extend `research-tree-setup --host hermes` with the
      dependency phase; no global config mutation, no bind mount.
- [x] 5.4 REFACTOR: manifest source under `skill-src/` flows into the
      generated package; parity check passes.

## 6. Focused + full gates

- [x] 6.1 Focused suites green: `tests/test_hermes_execution_adapter.py`,
      `tests/test_hermes_skill_compatibility.py`, `tests/test_skill_setup.py`,
      `tests/test_hermes_host_events.py`.
- [x] 6.2 Full governed suite passes (or unrelated failures explicitly
      reconciled against the recorded baseline set).

## 7. Live evidence (separate live-evidence subagent)

- [x] 7.1 Docker envelope preflight: official image digest resolved and
      recorded; setup container installs pinned deps into run-local
      `HERMES_HOME` volume.
- [x] 7.2 Two-child delegation batch through the project-mounted bridge;
      receipt contains actual identities, non-empty Finding Packs, hook
      events, ledger rows, image/config/dependency digests, redacted
      command.
- [x] 7.3 Fault-injected run: one child interrupted; recovery receipt shows
      `unknown` → new attempt while sibling stays accepted.
- [x] 7.4 Sanitized receipt + verifier replay path recorded under
      `.research-tree/evaluation-runs/issue-242/<run-id>/`.

## 8. Review and delivery

- [ ] 8.1 Independent reviewer in fresh worktree reruns focused suites,
      governed gates, and the receipt verifier; challenges identity binding.
- [ ] 8.2 One PR targeting `dev` with `Closes #242`; check-pr contract
      passes; GitNexus detect_changes reviewed.

## Rollback

`git revert` of the lane's delivery commits on
`feat/issue-242-hermes-delegation-lifecycle`.
