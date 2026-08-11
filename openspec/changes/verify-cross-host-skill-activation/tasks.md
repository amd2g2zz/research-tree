## 1. Red Contracts

- [x] 1.1 Add failing activation tests for three states, native paths, malformed markers, host/digest drift, safe receipts, and unavailable hosts.
- [x] 1.2 Run `uv run pytest -q tests/test_skill_activation.py`, `uv run ruff check tests/test_skill_activation.py`, and `uv run ruff format --check tests/test_skill_activation.py` after the red test.
- [x] 1.3 Add failing setup tests for all five statuses, no implicit rewrite, bounded refresh, and rollback.
- [x] 1.4 Run `uv run pytest -q tests/test_skill_setup.py`, `uv run ruff check tests/test_skill_setup.py`, and `uv run ruff format --check tests/test_skill_setup.py` after the red test.

## 2. Activation And Setup

- [x] 2.1 Implement states, canonical digests, pure probes, diagnostics, exact verification, receipts, and injectable native runner.
- [x] 2.2 Run `uv run pytest -q tests/test_skill_activation.py`, `uv run ruff check src/research_tree/skill_activation.py scripts/check_skill_activation.py tests/test_skill_activation.py`, and `uv run ruff format --check src/research_tree/skill_activation.py scripts/check_skill_activation.py tests/test_skill_activation.py`.
- [x] 2.3 Add link/reparse diagnostics, canonical-copy matching, and confirmed rollback-safe stale-link refresh.
- [x] 2.4 Run `uv run pytest -q tests/test_skill_setup.py tests/test_skill_activation.py`, Ruff lint over both implementations/tests, and Ruff format-check over the new activation module/script/test; legacy setup files retain baseline formatting.

## 3. Host Packages

- [x] 3.1 Add authoring activation rules and exact Codex/Claude/Hermes guidance through builder inputs only.
- [x] 3.2 Add package tests for host markers, helper parity, package/body digests, wrong-host material, and drift.
- [ ] 3.3 Run package/activation focused pytest and Ruff lint over the changed Python boundary; format-check the new activation module/script/test.
- [ ] 3.4 Rebuild/check with `uv run python scripts/build_skill_packages.py`, isolating `packages/` in a generated-only commit.

## 4. Group 32 Evidence

- [ ] 4.1 Run all native paths independently; real missing capabilities are `unavailable`.
- [ ] 4.2 Record source-bound output/receipt with exact three-command focused gate, revisions/digests, safe correlations, dispositions, and generated paths.
- [ ] 4.3 Mark only Alpha2 rows 8.8-8.11 and group 32 complete.

## 5. Delivery

- [ ] 5.1 Run focused pytest, Ruff lint over all changed Python, and `uv run ruff format --check src/research_tree/skill_activation.py scripts/check_skill_activation.py tests/test_skill_activation.py`.
- [ ] 5.2 Run full pytest, both strict OpenSpec validations, package check, governance, delivery, and `git diff --check`.
- [ ] 5.3 Inspect hard limits/generated separation, push, and open one `dev` PR with `Closes #71`; do not merge.
