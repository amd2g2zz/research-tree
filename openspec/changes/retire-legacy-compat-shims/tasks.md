# Tasks: retire-legacy-compat-shims

## 1. Shim Deletion

- [x] 1.1 `acceptance.py`: delete `LEGACY_HUMAN_KIND` and its detection branch.
- [x] 1.2 `evidence.py` (:381, :519) and `closure.py` (:764): delete the
  `legacy_unspecified` evidence-class branches.
- [x] 1.3 `readiness.py`: delete the dual-schema payload acceptance; require
  `risk_verification` and per-diagnostic `failure_category`.
- [x] 1.4 `coordinator.py`: delete both `insight_ref` → `insights_non_blocking`
  rename maps; delete `_legacy_to_regions` and the silent regions fallback in
  `self_state` (strict `_state_regions`, fail closed); delete the
  `ingest_event` compatibility wrapper; `debug_trace.py` reports the same
  single obligation name.
- [x] 1.5 `speech_acts.py`: delete `LEGACY_BELIEF_STATUSES`,
  `STATUS_LEGACY_MAP`, and the translation branch in `normalize_status`;
  `alignment_graph.py` checks its own `NODE_STATUSES` vocabulary first;
  `alignment_protocol.py` deletes its dead status set and predicate.
- [x] 1.6 `delivery.py`: `_anchor_label` renders strict typed evidence anchors
  only.
- [x] 1.7 `recursive_search.py` trigger label and `skill_setup.py` conflict
  reason code stop naming the retired concept; `cli.py` comment wording
  purged.
- [x] 1.8 `project_workspace.py`: delete `RUN_BOUND_LEGACY_ROOTS`,
  `UNATTRIBUTED_LEGACY_ROOTS`, the unattributed-root guard, and
  `_migrate_legacy_roots`; drop the `legacy` run directory and the
  `migrated_legacy_roots` manifest key; regenerate host packages.

## 2. Tests

- [x] 2.1 Delete old-behavior tests: two workspace-migration tests, the
  unattributed-root guard test, the legacy-class repository rejection block,
  and the legacy-evidence token denial test.
- [x] 2.2 Flip schema/vocabulary assertions: non-canonical-kind message,
  stale readiness record must be rejected, ingest guards via the canonical
  ingress, obligation names follow the manifold field name.

## 3. Verification And Handoff

- [x] 3.1 Run the full local gate battery: pytest (single known docker-env
  failure), ruff check + format, `build_skill_packages.py --check`,
  `check_openspec_governance.py`, `check_repository_layout.py`, and the
  retired-word grep gate (zero hits).
- [x] 3.2 Commit on `feat/issue-422-legacy-purge` in shim groups and push;
  PR and merge are owned by the coordinator.
