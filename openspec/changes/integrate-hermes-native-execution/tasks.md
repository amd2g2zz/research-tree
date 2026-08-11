## 1. Red contract tests

- [x] 1.1 Invert Hermes adapter tests so batches, reports, hooks, goals, and empty work cannot complete a run or write an authoritative local checkpoint.
- [x] 1.2 Add deterministic HostEvent, provider sanitization, safe-log, duplicate/conflict, sequence/revision, and raw-diagnostic red tests.
- [x] 1.3 Add restart unknown-before-retry, fault-prefix replay, bounded method-switch, and cross-host convergence red tests.
- [x] 1.4 Add Hermes goal/Kanban projection and authoring/generated package parity red tests.
- [x] 1.5 Run focused pytest, `uv run ruff check`, and `uv run ruff format --check` over every formatter-clean red slice.

## 2. Canonical Hermes translation and recovery

- [x] 2.1 Implement dependency-free Hermes HostEvent translation with canonical ids, digests, lineage, and whitelisted provider metadata.
- [x] 2.2 Compose coordinator recovery so unresolved attempts accept unknown outcome atomically before retry or an authorized replacement attempt.
- [x] 2.3 Implement replaceable goal/Kanban projections from canonical actions and acceptance criteria without write-back authority.
- [x] 2.4 Prove retries/method switches stay within coordinator-issued actions and run focused Ruff/TDD gates.

## 3. Thin adapter hooks and packages

- [x] 3.1 Replace `.research-tree-hermes/state.json`, batch/report completion, and Markdown shape gates with observation/projection compatibility commands.
- [x] 3.2 Keep runtime hooks sanitized, bounded, fail-open, and unable to ingest canonical lifecycle state directly.
- [x] 3.3 Update Hermes authoring references/adapter entry points without copying Codex/Claude package structure or claiming live activation.
- [x] 3.4 Rebuild/check generated packages, isolate generated output in generated-only commits, and run adapter/package Ruff gates.

## 4. Evidence and delivery

- [x] 4.1 Update group 9 execution/verification registries with focused pytest, Ruff, package, sanitization, retry, and crash receipts.
- [x] 4.2 Run the issue acceptance suite, full pytest, strict OpenSpec, package parity, governance, delivery validation, and `git diff --check`.
- [x] 4.3 Review scope, bind the receipt to the exact source revision, and keep #63/#71/#80/#82/#83 out of the PR.
