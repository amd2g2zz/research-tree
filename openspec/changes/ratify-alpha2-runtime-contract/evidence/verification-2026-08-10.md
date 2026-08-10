# Verification Evidence

- TDD red phase: `tests/test_alpha2_contract_ratification.py` failed because
  ADR-002 through ADR-005 were absent from `dev`.
- Focused ratification tests: 2 passed after adding the ADRs and registry checks.
- Strict OpenSpec validation: this change and `unify-research-runtime-alpha2`
  both valid.
- Governance validation: structurally valid, release not ready; all groups
  remain unverified as expected.
- Full regression: `uv run pytest -q` -> 290 passed.
- Host packages: Codex, Claude Code, and Hermes package checks valid.
- Scope: documentation/contract ratification only; no dependent runtime or
  Alpha2 release completion is claimed.
