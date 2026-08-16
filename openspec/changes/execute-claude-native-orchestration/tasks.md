## 1. Contract tests (RED)

- [x] 1.1 Add isolated Claude-package tests for Agent, Workflow, hybrid,
  fallback, and infeasible selection.
- [ ] 1.2 Add receipt-binding tests for native child/phase/session identities,
  replan quarantine, hook loss, and bounded hybrid delegation.
- [x] 1.3 Add package-isolation tests proving only Claude receives the bridge.

## 2. Claude bridge (GREEN)

- [x] 2.1 Implement the dependency-free selection and receipt validator.
- [x] 2.2 Add the bridge CLI and Claude-only package-builder mapping.
- [x] 2.3 Update Claude orchestration guidance with native receipt boundaries.

## 3. Verification

- [x] 3.1 Rebuild packages and run focused pytest plus package parity.
- [ ] 3.2 Run full pytest, Ruff, OpenSpec governance, delivery validation, and
  GitNexus changed-symbol detection.
- [ ] 3.3 Attempt live Claude CLI/Agent SDK evidence only when available; leave
  the live gate unavailable rather than substituting fixture evidence.
