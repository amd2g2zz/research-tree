# Tasks: adopt-two-layer-contract

## 1. Trace-type registry (RED first)

- [ ] 1.1 RED: `DEFAULT_TRACE_REGISTRY` contains exactly the six initial
  types (option-set, concept-card, guess-statement, counterargument,
  possibility-survey, evidence-delta) — no more, no less.
- [ ] 1.2 RED: registering a duplicate name raises `DuplicateTraceTypeError`
  naming the type; the original registry object stays unchanged (immutable
  rebind semantics, no unregister path).

## 2. Contract-terms schema (RED first)

- [ ] 2.1 RED: a valid contract round-trips through `to_dict`/`from_dict`
  with `schema_version` 1.
- [ ] 2.2 RED: `from_dict` rejects a missing field and an unknown field,
  each with the offending field named.
- [ ] 2.3 RED: `target_gap` and `taboos` entries must match the
  alignment-graph node-id shape; duplicates inside `taboos` /
  `required_traces` are rejected; unregistered required-trace names are
  rejected.
- [ ] 2.4 RED: `cost_cap` rejects unknown response classes; `discrimination`
  caps at exactly one sentence (一句指认); `generation` allows free text
  (unbounded or a positive explicit bound, never zero/negative).

## 3. verify_traces primitive (RED first)

- [ ] 3.1 RED: a required trace absent from the recorded set fails with
  `MissingTraceError` naming the exact missing term.
- [ ] 3.2 RED: a recorded trace whose type is not registered fails with a
  named schema error; a recorded trace of a required type missing declared
  payload fields fails with the field named.
- [ ] 3.3 RED: a satisfied contract returns the satisfied required traces;
  verification never inspects payload content beyond declared structural
  fields (a nonsense-text payload with the right keys passes).

## 4. Implementation (GREEN)

- [ ] 4.1 `src/research_tree/turn_contract.py`: trace types, frozen registry,
  contract-terms schema, `verify_traces`, errors; stdlib-only, zero new
  runtime dependencies, no imports from or into
  alignment_graph/decision_frame/lifecycle_hook.
- [ ] 4.2 GREEN: sections 1-3 pass; existing suites stay green.

## 5. check_impact_scope.py (RED first)

- [ ] 5.1 RED: pass case — a detect-changes JSON report whose changed files
  are all inside the declared `impact_scope` exits 0; fail case — one file
  outside the scope exits 1 and names the offender.
- [ ] 5.2 RED: git-diff fallback mode — `git diff --name-only base...HEAD`
  against tmp repos: in-scope passes, out-of-scope fails; malformed sidecar
  or report fails with a named schema error (deterministic, offline).

## 6. Implementation (GREEN)

- [ ] 6.1 `scripts/check_impact_scope.py`: sidecar schema
  (`impact-scope-v1`), detect-changes JSON consumption, documented git-diff
  fallback limitation, deterministic output.
- [ ] 6.2 GREEN: section 5 passes.

## 7. ADR + governance artifacts

- [ ] 7.1 `docs/adr/ADR-008-two-layer-contract.md` following the ADR-001..007
  format: context, decision, canonical contract-emission loop, design test,
  rejected design (behavior enumeration / 13-action menus / fixed selection
  ladders), consequences.
- [ ] 7.2 `.github/PULL_REQUEST_TEMPLATE.md`: Closes #N, OpenSpec change id,
  GitNexus impact report (HIGH/CRITICAL flagged), detect_changes↔impact_scope
  check, scenario→test mapping table, local gates.
- [ ] 7.3 `.gitignore`: `plan.md` under "# Local configuration".

## 8. Gates

- [ ] 8.1 Full local gates green: pytest (no new failures), ruff check +
  format, check_delivery_workflow validate, check_openspec_governance,
  build_skill_packages --check.
- [ ] 8.2 GitNexus `detect-changes --scope compare --base-ref dev`
  reconciled with `check_impact_scope.py` against this change's
  `impact_scope`; report stored in `evidence/`.
