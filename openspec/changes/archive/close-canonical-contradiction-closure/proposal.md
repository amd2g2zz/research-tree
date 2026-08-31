## Why

Independent corroboration does not prevent two otherwise admissible claims
from disagreeing. Current closure trusts worker-authored option effects and
does not propagate a canonical conflict into durable state.

## What Changes

- Derive normalized claim conflicts from canonical claim fields and persist a
  Contradiction Packet.
- Fail closure, readiness, and delivery when a selected decision depends on an
  unresolved material packet.
- Retract affected durable factual beliefs and pending actions through #246.
