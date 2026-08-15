## 1. Contract Tests

- [x] 1.1 Add RED tests for project/run initialization, identifier validation,
  and isolated lifecycle event placement.
- [x] 1.2 Add RED tests for idempotent Codex/Claude merging, rollback, and
  project-local Hermes configuration.

## 2. Implementation

- [x] 2.1 Implement the workspace descriptor and atomic filesystem helpers.
- [x] 2.2 Implement project hook bootstrap and configuration verification.
- [x] 2.3 Bind lifecycle observer output to validated workspace descriptors.

## 3. Verification

- [x] 3.1 Run focused and full regression suites, Ruff, OpenSpec, package, docs,
  and delivery governance checks.
- [x] 3.2 Inspect GitNexus change impact before commit and open one `dev` PR.
