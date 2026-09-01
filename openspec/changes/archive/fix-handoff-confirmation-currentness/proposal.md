## Why

The legacy alignment controller confirms a displayed graph digest, then later
rebuilds the handoff from mutable graph state. A post-confirmation mutation can
therefore change the resulting authority, scope, or closure oracle without a
new human confirmation.

## What Changes

Bind a handoff confirmation to the digest of the confirmed graph state, mark a
confirmed handoff stale when alignment state mutates, and reject a compiled or
adapter-loaded handoff whose confirmed and compiled graph digests differ.

## Impact

- Affects the alignment-controller source and generated host packages.
- Adds fail-closed native and Hermes adapter checks for stale handoff artifacts.
- Requires an explicit successor confirmation after a post-confirmation graph
  mutation.
