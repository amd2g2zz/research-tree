# Verification Evidence

- Focused importer, CAS, SQLite, and governance tests: 30 passed.
- Full regression: `uv run pytest -q` -> 288 passed.
- Strict OpenSpec validation: `import-alpha1-runstore` and
  `unify-research-runtime-alpha2` both valid.
- Governance: `check_openspec_governance.py` valid; group 34 remains
  `in_progress` until PR merge/evidence promotion.
- Host packages: `build_skill_packages.py --check` reports Codex, Claude Code,
  and Hermes valid.
- Scope retained: filesystem RunStore only; all imported claims are historical
  and unverified. Alignment/native/Hermes migration and legacy revalidation are
  not claimed by this change.
