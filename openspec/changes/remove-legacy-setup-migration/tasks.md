## 1. Contract And Governance

- [x] 1.1 Define current-only setup behavior and the no-mutation boundary for
  existing non-current targets.
- [x] 1.2 Register group 57 / issue #169 as a planned setup-retirement slice.
- [x] 1.3 Archive the completed #71 activation change without synchronizing its
  retired setup delta, then repoint the #71 registry evidence to history.

## 2. Focused Regressions

- [x] 2.1 Replace prior-version behavior tests with no-mutation rejection tests
  for checkout-root and old Claude package links.
- [x] 2.2 Add parser and public-surface regressions proving refresh and
  migration outcomes are absent while missing/current installs still work.

## 3. Current-Only Setup Implementation

- [x] 3.1 Remove legacy source recognition, migration actions, and all
  existing-target replacement from install and status paths.
- [x] 3.2 Remove stale-link refresh helpers, CLI registration, and confirmation
  options without changing current host layouts.
- [x] 3.3 Rebuild packages from source only if maintained package content
  changes, keeping generated output separate from source commits.

## 4. Verification And Handoff

- [x] 4.1 Run the group-57 focused acceptance command, strict OpenSpec, and
  package validation.
- [x] 4.2 Run the full suite, governance checks, and `git diff --check`.
- [x] 4.3 Record the source-bound group-57 receipt only after its acceptance
  command succeeds.
- [x] 4.4 Prove the active umbrella contract reports non-current targets as
  unsupported and publishes no stale-link refresh behavior.
