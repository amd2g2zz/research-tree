# Tasks: merge-dispute-into-contradictions

## 1. Module Merge

- [x] 1.1 `contradictions.py`: move the retained dispute symbols verbatim into
  a marked section; merge imports; extend the module docstring; merge
  `__all__`.
- [x] 1.2 `coordinator.py`: merge the 11 dispute-symbol imports into the
  existing `from .contradictions import` block; no other change.
- [x] 1.3 Delete `src/research_tree/dispute.py`.

## 2. Tests

- [x] 2.1 Rename `tests/test_dispute_governance.py` to
  `tests/test_contradictions_dispute_governance.py`; switch the import source;
  keep every assertion.
- [x] 2.2 Add negative lockout tests: the `research_tree.dispute` module is
  gone, and the four retired entrypoints are absent from the merged module
  and its `__all__`.

## 3. Surfaces Checked

- [x] 3.1 `__init__.py`: no dispute re-exports exist; nothing to change.
- [x] 3.2 Governance registries: zero dispute references in both registry
  directories; no registry command references DISPUTE_PACKET_KIND artifacts;
  nothing to change.
- [x] 3.3 Skill packages: `packages/**` skill scripts are self-contained and
  never import `research_tree`; no regeneration needed (verified by
  `build_skill_packages.py --check`).
