# Alpha2 Final Delivery Plan: #84 Then #67

**Issue ownership:** `#84` owns the benchmark implementation, sealed run, and one PR to `dev`. `#67` owns only the post-merge release-definition audit and one PR to `dev`; it must not absorb #84 implementation.

**CI contract:** `.github/workflows/delivery-governance.yml` runs `scripts/check_delivery_workflow.py validate`, `scripts/check_openspec_governance.py`, `scripts/build_skill_packages.py --check`, changed-file Ruff, and `check-pr --event` for PRs to `dev` or `master`.

**Docker contract:** `evaluation/docker/compose.yaml` gives the runner only internal broker/source/simulator networks; broker and source services alone have egress networks. The runner is non-root, read-only, capability-dropped, no-new-privileges, PID/memory/CPU bounded, and has no host volume or secret.

**Harness gates:** Group 30 in `openspec/changes/unify-research-runtime-alpha2/tasks.md` is #84 authority. Raw runs remain ignored under `.research-tree/evaluation-runs/`; only redacted, reproducible provenance is tracked.

## 1. Deliver #84 On Its Existing Branch

1. Keep `test/issue-84-paired-benchmark` rebased on `origin/dev`; preserve one issue, branch, worktree, and PR.
2. Finish the sealed three-arm, two-host protocol: freeze model/runtime/intervention/binding/rootfs and paired runner/synthetic-user inputs; reject mismatches before launch.
3. Use the evaluator-owned SQLite journal for every attempt. Require append-only, HMAC-attested events, contract verification before launch, boundary-only recovery, and external redacted logs. Never resume agent memory, synthetic-user conversation, source state, or writable guest filesystem.
4. Run the Docker internal-network smoke, deterministic integrity corpus, and a bounded live baseline pilot only through an externally supplied credential file. Record actual provider usage and retain raw evidence only under the ignored run root.
5. Complete a sealed, stratified three-arm corpus with paired CIs, separate integrity outcomes, budget diagnostics, disagreement-preserving blinded review, and an explicit unavailable disposition for any missing host rather than an inferred pass.
6. Update Group 30 task/registry/receipt evidence only after the final branch head passes targeted tests, full tests, Ruff, OpenSpec, governance/docs/package checks, `git diff --check`, delivery preflight, and GitNexus change detection.
7. Open one non-WIP PR to `dev` with `Closes #84`; wait for CI, merge only after the delivery contract passes, then verify `origin/dev` contains the merge and #84 is closed.

## 2. Deliver #67 After #84 Is Merged

1. Create a fresh `docs/issue-67-alpha2-release-audit` worktree from the merged `origin/dev`; do not reuse #84's branch.
2. Recompute the Epic release-definition audit from current `dev`: all P0 issues closed, #72/#84 evidence reachable, host parity and recovery evidence resolved, generated packages/docs/layout/governance checks pass, and no raw/private evidence is tracked.
3. If any release criterion lacks direct evidence, leave #67 open and report the exact failed criterion; do not manufacture a pass from harness structure or synthetic data.
4. When all criteria pass, add only the redacted #67 final audit, its OpenSpec/registry receipt, and focused regression assertions. Run the same delivery gates and GitNexus review.
5. Open one PR to `dev` with `Closes #67`, merge after CI, verify the merged head is reachable from `dev`, and close the Epic. `master` remains untouched throughout.

## Completion Evidence

- #84: merged PR, closed issue, final raw evidence outside Git, tracked provenance that validates the exact branch head, and direct proof of every listed acceptance criterion.
- #67: merged PR, closed Epic, release-definition audit tied to the merged #84 revision, and all delivery/governance/package/layout checks green on `dev`.
