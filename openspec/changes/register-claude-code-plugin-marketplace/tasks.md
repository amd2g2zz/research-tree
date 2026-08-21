## 1. Contract Tests

- [x] 1.1 Add red tests for marketplace/plugin manifest shape, source path,
  version consistency, and native nested Skill layout.
- [x] 1.2 Add red tests proving Codex and Hermes packages remain free of Claude
  plugin metadata and that direct Claude installation resolves the nested Skill.

## 2. Metadata and Package Builder

- [x] 2.1 Add repository-owned Claude plugin and marketplace metadata under
  `skill-src/`.
- [x] 2.2 Update `build_skill_packages.py` to generate the repository
  marketplace, the nested Claude package, and plugin metadata.
- [x] 2.3 Extend package validation and `--check` output for JSON validity,
  source/name/version consistency, stale output, and host isolation.
- [x] 2.4 Regenerate checked-in Claude package artifacts without changing Codex
  or Hermes layouts.

## 3. Installer and Documentation

- [x] 3.1 Make `research-tree-setup` validate the Claude plugin root and install
  `skills/research-tree/` as the direct Claude Skill payload.
- [x] 3.2 Update Claude compatibility references and README with marketplace,
  local validation, direct-install, and static-vs-live activation guidance.
- [x] 3.3 Confirm the existing delivery workflow covers package changes and
  add regression assertions for marketplace and plugin artifacts.

## 4. Verification and Handoff

- [x] 4.1 Run focused red/green tests, full pytest, compileall, OpenSpec strict
  validation, package parity, and the delivery workflow.
- [x] 4.2 Run `claude plugin validate` when the Claude CLI is available and
  record unavailable host tooling honestly when it is not.
- [x] 4.3 Commit the completed slice atomically, push the issue branch, and
  open one PR targeting `dev` with `Refs #70`.
