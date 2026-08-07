## Scope
Closes #55
OpenSpec: `establish-replayable-alpha1-adversarial-baseline`
Base: `dev@904ca6f9e1c254587e50bd5235be9b7b4997f396`

This draft delivers replayable Alpha1 adversarial-baseline evidence for all
nine issue #55 defect identifiers:

- six independent `vulnerability_reproduced` receipts;
- three executable pending counterexample receipts whose unsafe predicates were
  not observed;
- a governed manifest that does not count pending cases as coverage;
- distinct raw and redacted command-stream digests;
- caller-owned replay roots that remain empty after default cleanup.

No Alpha2 fix confirmation is claimed.

## Acceptance evidence

| Criterion | Black-box evidence | Automated regression |
| --- | --- | --- |
| Filler report reaches unsafe Alpha1 completion | Pinned Hermes replay; `vulnerability_reproduced` receipt | `tests/test_alpha1_adversarial_replay.py` |
| Forged validation accepts passed status with missing evidence | Pinned Claude native replay; evidence path resolves false | `tests/test_alpha1_adversarial_replay.py` |
| Missing-evidence completion is independent | Seven-command Claude lifecycle without `validation_result`; unresolved review anchor still completes | `tests/test_alpha1_missing_evidence.py` |
| State/trace cases are case-bound | Active contradiction, repeated reconnaissance, and adapter-only completion reproduce; empty frontier remains pending because Alpha1 blocks | `tests/test_alpha1_state_trace.py` |
| Provider/crash obligations are explicit | Failed/in-flight obligations remain present, ready, and retryable; lost predicate is false | `tests/test_alpha1_recovery.py` |
| Every named defect is tracked without false coverage | Nine-entry manifest: 6 executable, 3 pending evidence-backed counterexamples | `tests/test_alpha1_baseline.py` |
| Baselines cannot claim a fix | Receipts and manifest reject `fix_confirmed` | Focused replay and manifest tests |

## Three-agent implementation loop

Three disjoint agents implemented and independently reported:

- missing-evidence replay and fixture validation;
- state/trace replay for empty frontier, active contradiction, repeated
  reconnaissance, and adapter-only completion;
- provider-failure and crash-recovery boundary receipts with lost/recovered
  obligation predicates.

Each followed TDD red→green, was constrained to owned paths, ran GitNexus
impact before existing-symbol edits, and ran `detect_changes()` before return.
New harness symbols were absent from the canonical GitNexus index, so those
lookups were recorded as `UNKNOWN`, not treated as invented low-risk results.
No HIGH or CRITICAL blast radius was reported.

## Verification

- [x] focused replay/contract tests — 26 passed after cleanup reconciliation
- [x] `uv run --frozen pytest -q` — 286 passed locally
- [x] `openspec validate --all --strict` — 4 passed, 0 failed
- [x] `scripts/check_openspec_governance.py` — valid, `release_ready: false` because unrelated groups remain unverified
- [x] package parity — all codex/claude/hermes packages valid
- [x] `check_delivery_workflow.py validate` — valid
- [x] `git diff --check`
- [ ] `check-pr` — blocked by hard review limit
- [ ] GitHub Actions checks — unavailable with viewer permission `READ`

## Risks, rollback, and delivery blockers

- Three pending receipts are deliberately not defect reproductions:
  `empty-frontier` blocked instead of completing, and provider/crash recovery
  preserved retryable obligations. The corpus therefore has six reproduced
  unsafe predicates and three non-reproduced pending predicates.
- The local PR gate reports `hard_review_limit_exceeded`: **52 non-generated
  files / 5,017 non-generated lines**. Policy requires a maintainer-approved
  exception above 1,500 lines; none is recorded. This branch is not ready for
  review until the change is split or an explicit approved exception is added.
- Push/PR creation is blocked by remote permission: `git push --dry-run` for
  `test/issue-55-adversarial-baselines` returns HTTP 403 (`Permission to
  amd2g2zz/research-tree.git denied to edmserver`). No remote PR or CI result is
  claimed.

## Follow-up state

- 3.4a governed nine-defect manifest: complete.
- 3.4b raw/redacted digest migration: complete.
- 3.4c cleanup/help reconciliation: complete; caller-owned roots remain empty.
- Delivery 4.3 remains blocked until GitHub WRITE permission is available and
  the review-size policy is resolved.
