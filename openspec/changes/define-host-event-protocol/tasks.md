## 1. Red contract tests

- [x] 1.1 Add envelope/event-specific validation, digest, unsupported-version,
  path-normalization, and sequence-gap red tests in
  `tests/test_host_event_protocol.py`.
- [x] 1.2 Add duplicate/conflict, stale/orphan attempt, crash-prefix, and
  non-authoritative completion red tests to `tests/test_research_run_coordinator.py`.
- [x] 1.3 Invert native adapter tests so local task/report/empty-work signals
  cannot complete a run; add Codex/Claude semantic-digest parity cases.
- [x] 1.4 Add package source/generated parity red tests in
  `tests/test_skill_packages.py`.
- [x] 1.5 Run focused pytest, `uv run ruff check`, and
  `uv run ruff format --check` over each new test slice.

## 2. Typed ingestion

- [x] 2.1 Add immutable `HostEvent` and event-specific payload validators in
  `src/research_tree/host_events.py`.
- [x] 2.2 Add atomic typed ingestion to `ResearchRunCoordinator` with exact
  revision, attempt, sequence, duplicate, and rejection handling.
- [x] 2.3 Prove no host event can satisfy closure/readiness/delivery/acceptance/
  completion and run changed-file Ruff gates.

## 3. Thin adapters and packages

- [x] 3.1 Refactor native Codex/Claude adapters to emit shared envelopes and
  retain only observation/text fallback behavior.
- [x] 3.2 Remove adapter-local completion/report authority and update maintained
  orchestration references without implementing Hermes/workflow changes.
- [x] 3.3 Rebuild/check generated packages and run adapter/package Ruff gates.

## 4. Evidence and acceptance

- [ ] 4.1 Update group 8 task/verification registry with protocol, focused pytest,
  Ruff, package, and crash fixture receipts.
- [x] 4.2 Run focused suite, full pytest, strict OpenSpec, package parity,
  governance, delivery validation, and `git diff --check`.
- [ ] 4.3 Review scope and mark tasks only with source-bound evidence before one
  PR closing #60.
