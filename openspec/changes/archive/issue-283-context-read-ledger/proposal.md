# Bounded Context-Read Ledger

## Why

The senior-user evaluation observed 14M--17M input-token runs whose cached
input dominated the total. Repeated acquisition and process output were not
durably visible, active run logs could be reread as source material, and no
budget exhaustion oracle made an over-budget result fail closed.

## What Changes

- Add a run-scoped ledger recording source digest, byte and line range,
  consumer, phase, disposition, and token/output cost for every source read.
- Classify unchanged repeated reads as `cached` for the same consumer or
  `replayed` for a different consumer; never silently collapse the duplicate.
- Exclude active run outputs from discovery and reads until a digest-bound seal
  explicitly admits the file.
- Enforce configurable per-wave input/output and duplicate-ratio budgets.
  Exhaustion emits a resumable `budget_exceeded` checkpoint with execution
  state `unknown`, never a completion or pass state.
- Project the same receipt contract through native Codex/Claude and Hermes
  adapters, and add a diagnostic-only comparison oracle for duplicate reduction
  with retained digest-range coverage.

## Non-goals

- Estimating semantic research quality from token counts or declaring research
  complete from a context-cost receipt.
- Claiming live Codex, Claude, or Hermes lifecycle evidence from a local adapter
  regression test.

## Impact

- Affects source runtime APIs, native host adapter command surfaces, generated
  skill packages, host guidance, OpenSpec, and regression coverage.
