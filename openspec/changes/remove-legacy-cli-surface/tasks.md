## 1. Contract And Governance

- [x] 1.1 Define the breaking removal of legacy command and migration
  surfaces, including the #165 runtime-retirement boundary.
- [x] 1.2 Register group 54 / issue #164 as a planned breaking-removal slice.

## 2. Focused Regressions

- [x] 2.1 Replace containment tests with parser-rejection and help-discovery
  regressions for every retired `research-tree` command.
- [x] 2.2 Add retirement checks for migration metadata, modules, exports, and
  path-free parse failures.

## 3. Public-Surface Removal

- [x] 3.1 Remove all legacy `research-tree` parser registrations, dispatch,
  compatibility responses, read-only paths, and legacy-only imports.
- [x] 3.2 Remove the standalone Alpha1 migration console script, modules,
  exports, tests, and workflow-probe invocation.
- [x] 3.3 Remove retired command references from maintained documentation and
  templates, then rebuild generated host packages.

## 4. Verification And Handoff

- [x] 4.1 Run focused CLI, legacy-import regression, layout, package, and
  formatting checks.
- [x] 4.2 Run the full suite, strict issue and umbrella OpenSpec validation,
  governance check, package check, and `git diff --check`.
- [ ] 4.3 Record source-bound group-54 verification only after its acceptance
  evidence is available.
