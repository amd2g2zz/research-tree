## 1. Tree-state phase discriminator (RED first)

- [ ] 1.1 RED: every illegal phase transition (25 parametrized pairs) is
  rejected by `CanonicalResearchTreeStateService.transition` with a named
  error; legal edges and self-loops pass.
- [ ] 1.2 RED: unknown `phase` values, non-`compiled` birth phases, and
  malformed optional keys are rejected by `validate_tree_state_payload`;
  legacy payloads without `phase` stay valid.

## 2. Post-compile realignment gate (RED first)

- [ ] 2.1 RED: a `strategy_authority_fingerprint` change without a
  `realignment` record is rejected; with the record on the
  `alignment → compiled` edge it is accepted; on any other edge it is
  rejected even with a record; fingerprint drop and record/fingerprint
  mismatch are rejected.

## 3. Implementation (GREEN)

- [ ] 3.1 `tree_state.py`: `TREE_PHASES`, `DEFAULT_TREE_PHASE`,
  `TREE_PHASE_TRANSITIONS`, `tree_phase_of`, payload validation for the
  three optional keys, birth-phase gate, transition phase gate,
  realignment gate.
- [ ] 3.2 GREEN: sections 1-2 pass; existing recursive-search and
  handoff suites stay green.

## 4. Two-option re-entry protocol (RED first)

- [ ] 4.1 RED: `resolve_research_reentry` maps reopen / supplemental /
  status prompts to their named paths and refuses drift and bare
  interruptions (`research_reentry_refused`).
- [ ] 4.2 RED: with run phase `research`, `observe` records the re-entry
  resolution on the signal record and routes it to the run events surface;
  outside research the gate is inactive; invalid explicit phase raises,
  invalid env/manifest phase is ignored.

## 5. Implementation (GREEN)

- [ ] 5.1 `lifecycle_hook.py`: phase source chain
  (argument → `RESEARCH_TREE_RUN_PHASE` → manifest), `RUN_PHASES`,
  re-entry rule table, run-events feed generalized with
  `route: "research_reentry"`.
- [ ] 5.2 GREEN: section 4 passes; existing lifecycle-hook suites stay green.

## 6. Prompt layer

- [ ] 6.1 Replace the internal-successor-revision clause in
  `skill-src/SKILL.template.md` and `skill-src/hermes-SKILL.template.md`
  with the realignment requirement and the two-option re-entry protocol.
- [ ] 6.2 Regenerate `packages/**` with
  `uv run --frozen python scripts/build_skill_packages.py` and commit the
  regenerated artifacts.

## 7. Gate

- [ ] 7.1 Full local gates green (pytest, ruff check + format,
  delivery workflow validate, openspec governance, package parity) and
  GitNexus detect_changes reconciled against `impact_scope`; open PR to dev.
