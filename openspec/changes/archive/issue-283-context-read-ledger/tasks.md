## 1. Durable bounded reads

- [x] 1.1 Record digest, byte/line range, consumer, phase, disposition, and
  fresh/cached/replayed input plus tool/process output costs.
- [x] 1.2 Exclude active outputs and dependency/cache roots until a source is
  explicitly digest-sealed.
- [x] 1.3 Emit resumable `budget_exceeded` checkpoints with unknown execution
  state and no completion authority.

## 2. Adapter and evaluation projections

- [x] 2.1 Add bounded read, seal, receipt, and resume commands to native and
  Hermes adapters.
- [x] 2.2 Add an evaluation-only duplicate-reduction diagnostic that requires
  digest-range coverage retention.
- [x] 2.3 Package the dependency-free contract for Codex, Claude Code, and
  Hermes and document host usage.

## 3. Regression and delivery

- [x] 3.1 Cover duplicate classification, active-output sealing, budgets,
  resume semantics, cost diagnostics, and each adapter's exit projection.
- [ ] 3.2 Run package, lint, OpenSpec, governance, and delivery checks; push
  the issue branch and open its PR.
