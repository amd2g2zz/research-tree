## 1. Contract And Governance

- [x] 1.1 Define current-only setup behavior and the no-mutation boundary for
  existing non-current targets.
- [x] 1.2 Register group 57 / issue #169 as a planned setup-retirement slice.

## 2. Focused Regressions

- [ ] 2.1 Replace legacy migration tests with no-mutation rejection tests for
  checkout-root and old Claude package links.
- [ ] 2.2 Add parser and public-surface regressions proving refresh and
  migration outcomes are absent while missing/current installs still work.

## 3. Current-Only Setup Implementation

- [ ] 3.1 Remove legacy source recognition, migration actions, and all
  existing-target replacement from install and status paths.
- [ ] 3.2 Remove stale-link refresh helpers, CLI registration, and confirmation
  options without changing current host layouts.
- [ ] 3.3 Rebuild packages from source only if maintained package content
  changes, keeping generated output separate from source commits.

## 4. Verification And Handoff

- [ ] 4.1 Run the group-57 focused acceptance command, strict OpenSpec, and
  package validation.
- [ ] 4.2 Run the full suite, governance checks, and `git diff --check`.
- [ ] 4.3 Record the source-bound group-57 receipt only after its acceptance
  command succeeds.
