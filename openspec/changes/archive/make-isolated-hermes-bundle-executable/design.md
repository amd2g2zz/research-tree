## Context

`build_skill_packages.py` owns the generated Hermes package contents while
`hermes_skill_adapter.py` stages a GitHub-installable copy.  The adapter derives
its copy list from backticked Markdown resources, which cannot express Python
module imports.  `hermes_execution_adapter.py` falls back from an installed
`research_tree` import to `native_workflow_contract.py`; that sibling exists in
the checked-in package but is omitted by staging.

## Goals / Non-Goals

**Goals:**

- Define a single explicit, deterministic executable closure for Hermes.
- Use it for package construction, validation, staging, and isolated cold-start
  tests.
- Make compatibility fail closed on missing executable dependencies.
- Keep staged provider-recovery behavior runnable without the repository.

**Non-Goals:**

- Dynamic import graph discovery, execution of arbitrary skill documents, or
  copying the source tree into the package.
- Changing canonical coordinator authority, HostEvent semantics, or Hermes
  runtime hooks.

## Decisions

1. **Declare a small static closure.** The documented entrypoints and their
   known sibling modules are finite.  An explicit tuple is reviewable and
   reproducible; runtime import tracing would depend on ambient state and miss
   conditional paths.
2. **Validate through actual subprocess cold starts.** Static existence checks
   catch omission early, but subprocess execution catches broken imports and
   accidental source-checkout leakage.  The validation subprocess strips
   `PYTHONPATH`, runs from an unrelated temporary directory, and invokes only
   `--help` to avoid lifecycle mutation.
3. **Reuse one closure in builder and stage.** Duplicated resource lists caused
   the defect.  Both paths consume a shared exported function/constant, then
   validation verifies exact expected files.
4. **Test recovery with a bounded fixture.** A minimal canonical-attempt JSON
   exercises the fallback import and recovery code without a live provider or
   untrusted network dependency.

## Risks / Trade-offs

- **[Risk] A future documented script is omitted from the declaration** ->
  derive the validation entrypoint list from the same closure and test every
  documented executable reference.
- **[Risk] Environment leakage masks an import** -> execute with a sanitized
  environment, isolated CWD, and explicit assertion that source root is absent
  from `sys.path`.
- **[Risk] Windows process quoting differs** -> invoke `sys.executable` with
  an argument list rather than a shell command.

## Migration Plan

1. Add red isolated staging and missing-dependency tests.
2. Add the closure declaration, wire it into build/stage/validation, and
   rebuild generated packages.
3. Run focused and full package suites, strict OpenSpec, and source-bound
   acceptance checks.

Rollback reverts the generated package and closure changes together; a package
that cannot cold-start remains incompatible rather than publishing a partial
bundle.

## Open Questions

No live Hermes host is required for this package-closure contract.  Live host
availability remains a separate release-gate concern.
