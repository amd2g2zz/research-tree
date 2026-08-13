## 1. Contract And Governance

- [x] 1.1 Register issue #173 / group 59 with the strict reader acceptance
  command and current-only rollback boundary.
- [x] 1.2 Archive the completed active preference-profile change that mandates
  legacy strategy-projection reads, preserving its evidence as history.

## 2. Focused Regressions

- [x] 2.1 Replace legacy-read coverage with failing tests that prove canonical
  writer payloads round-trip and missing-field prior payloads reject.
- [x] 2.2 Update all direct current `StrategyProjection.create` fixtures to
  provide explicit `preference_influences`.

## 3. Strict Reader Removal

- [x] 3.1 Delete direct-construction default inference for
  `preference_influences`.
- [x] 3.2 Delete prior-shape parser, alternate digest path, and legacy reader
  branch while retaining exact canonical integrity checks.
- [x] 3.3 Remove active contract language that advertises compatibility reads,
  aliases, defaults, migrations, or projection fallbacks.

## 4. Verification And Handoff

- [x] 4.1 Run the group-59 focused acceptance command, strict OpenSpec
  validation, governance validation, and relevant regression checks.
- [ ] 4.2 Commit source changes, rebase on current `origin/dev`, and resolve
  shared registry conflicts before recording evidence.
- [ ] 4.3 Record the source-bound group-59 receipt, mark its registry entry
  verified, and run final full validation and diff checks.
