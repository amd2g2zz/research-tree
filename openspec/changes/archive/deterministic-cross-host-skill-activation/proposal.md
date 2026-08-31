## Why

Loader integrity is necessary but does not decide whether a host may begin
research. The three supported harnesses need one deterministic, fail-closed
activation contract so implicit acknowledgements cannot start autonomous work.

## What Changes

- Add one host-neutral activation gate after loader verification.
- Make all three skill templates state positive and negative triggers, ordered
  alignment/handoff phases, and bounded error handling.
- Test Codex, Claude, and Hermes using the same gate and package parity checks.

## Non-goals

- Change canonical coordinator or alignment semantics.
- Add Docker or host-specific runtime dependencies.
- Replace #269 loader evidence or #271 fault injection.
