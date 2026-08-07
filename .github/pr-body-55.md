## Scope
Closes #55
OpenSpec: `establish-replayable-alpha1-adversarial-baseline`
Base: `dev@904ca6f9e1c254587e50bd5235be9b7b4997f396`

This draft delivers the next reviewable Alpha1 adversarial-baseline slices:

- replayable Hermes filler-report baseline;
- replayable Claude forged-validation baseline;
- one governed manifest covering all nine named defects;
- explicit pending states for the seven cases without independent semantic receipts.

## Acceptance evidence

| Criterion | Black-box evidence | Automated regression |
| --- | --- | --- |
| Filler report reaches unsafe Alpha1 completion | Agent 1 and Agent 2 isolated replay; `vulnerability_reproduced` receipt | `tests/test_alpha1_adversarial_replay.py` |
| Forged validation accepts passed status with missing evidence | Agent 2 native adapter replay; evidence path resolves false | `tests/test_alpha1_adversarial_replay.py` |
| Every named defect is tracked without false coverage | Nine-entry governed manifest; 2 executable, 7 pending | `tests/test_alpha1_baseline.py` |
| Baselines cannot claim a fix | Receipts and manifest reject `fix_confirmed` | focused replay and manifest tests |

## Three-agent findings

- Operational black-box: setup and filler replay pass; committed baseline was 1/9 before this slice; receipt digest/redaction and cleanup wording gaps remain.
- Domain black-box: forged validation is reproducible; missing evidence, adapter-only completion, repeated reconnaissance, provider failure, and crash recovery have symptoms but lack independent case-bound receipts; empty frontier and active contradiction remain unverified.
- Root cause / TDD regression: red→green forged-validation harness and manifest contract; new symbols were not in the current GitNexus index, so impact was `UNKNOWN` rather than invented.

## Verification

- [x] focused replay and manifest tests
- [x] `uv run --frozen pytest -q` — 270 passed locally
- [x] `openspec validate --all --strict`
- [x] `scripts/check_openspec_governance.py`
- [x] package parity
- [x] local delivery policy and `check-pr`
- [x] `git diff --check`
- [ ] GitHub Actions checks — unavailable with viewer permission `READ`

## Risks, rollback, and follow-ups

- This PR must remain draft/open: seven of nine issue #55 defects are explicitly pending and no Alpha2 fix is claimed.
- `tests/test_alpha1_baseline.py` now satisfies the registered group-1 acceptance command without pretending pending cases are green.
- The local delivery gate currently reports `hard_review_limit_exceeded` (24 non-generated files / 1,612 non-generated lines). A maintainer-approved exception is required by policy; none exists, so this draft is not ready for review. Split the remaining defect cases and/or obtain an explicit recorded exception before requesting review.
- Push/PR creation is blocked by remote permission: `git push --dry-run` returned HTTP 403 (`Permission to amd2g2zz/research-tree.git denied to edmserver`).
- Next slices: missing-evidence independent case, state/trace cases, provider/crash boundaries, raw/redacted receipt migration, and cleanup help reconciliation.
