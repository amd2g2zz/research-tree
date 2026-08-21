## Why

Strict Readiness currently proves that a Decision and Finding agree with each
other, but not that they belong to the Technical Package's canonical
Blueprint Target. A foreign, internally consistent ledger subgraph can
therefore pass closure; this is the remaining post-#108 boundary gap.

## What Changes

- Bind strict Finding and selected/conditional Decision payloads to the
  package-resolved Blueprint Target before evidence authorization.
- Fail strict closure and implementation readiness for a foreign Target.
- Add a public-path fault-injection regression and OpenSpec contract.

## Capabilities

### New Capabilities

- `package-target-bound-readiness`: Strict readiness is rooted in the exact
  Blueprint Target resolved from the Technical Package.

### Modified Capabilities

- None. The #108 change remains the historical strict evidence boundary.

## Impact

- `src/research_tree/readiness.py` receives the package Target at strict
  evidence authorization.
- Focused readiness tests and a small OpenSpec change are added.
- No DeliveryCompiler, evidence schema, or host-package behavior changes.
