## 1. Migration And Shrinkage

- [x] 1.1 Relocate `src/research_tree/release_evaluation.py` to
  `evaluation/harness/release_evaluation.py` byte-identical (`git mv`); the
  module is import-self-contained (stdlib only), so no in-module path edits.
- [x] 1.2 Shrink `src/research_tree/evaluation.py` from 701 to 400 lines to the
  production-consumed surface (BLUEPRINT_EVALUATION_KIND +
  validate_blueprint_evaluation_payload via completion_inputs) plus direct
  dependencies; delete BlueprintEvaluationSuite, EvaluationCheck,
  IndependentEvaluationRequest/Result, IndependentImplementationRunner,
  SimplerBaselineResult, and the suite-only helpers.
- [x] 1.3 Remove the `release_evaluation` re-export block and 12 `__all__`
  entries; shrink the `evaluation` re-export block to the 6 surviving symbols.
- [x] 1.4 Repoint `run_release_gates.py` at its harness sibling
  (`from release_evaluation import ...`, run_host_conformance precedent).

## 2. Tests And References

- [x] 2.1 `tests/test_black_box_release.py` and `tests/test_release_manifest.py`
  adopt the harness sys.path precedent for the relocated module and runner.
- [x] 2.2 `tests/test_evaluation_suite.py`: keep the public-case-set contract
  and TimeSplitCase hidden-material-rejection cases; delete the 5
  BlueprintEvaluationSuite-anchored cases with their private fixtures.

## 3. Verification And Handoff

- [x] 3.1 Run the full local gate battery: pytest, ruff check + format,
  `build_skill_packages.py --check`, `check_openspec_governance.py`,
  `check_docs.py`, `check_repository_layout.py`, `openspec validate
  migrate-release-evaluation-harness --strict`, moved-path and zero-hit greps.
- [x] 3.2 Commit in waves on `feat/issue-425-release-eval-harness` and push;
  PR and merge are owned by the coordinator.
