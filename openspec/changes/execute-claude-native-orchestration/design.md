## Context

The package is dependency-free and runs inside an active Claude Code session.
It may validate observations from that session but must not spawn a second
Claude CLI to imitate native Agent or Workflow invocation.

## Design

`claude_orchestration_contract.py` owns two pure operations:

1. `select_mode` accepts explicit capability observations and an optional
   requested mode.  It returns one of `agent`, `workflow`, `hybrid`, or
   `infeasible`, with a digest-bound selection reason.  `auto` prefers hybrid
   when both surfaces are observed available, otherwise the available single
   surface.  Workflow absence never suppresses an available Agent path.
2. `bind_receipt` accepts a selected plan and a native runtime receipt.  It
   rejects synthetic IDs, missing provider/session/version provenance,
   insufficient phases/children, mode mismatch, uncontrolled nesting, and
   malformed digests.  A valid bridge record is explicitly non-authoritative
   and maps native identities to canonical action/attempt bindings.

The contract is packaged only for Claude.  The package builder copies it from
`scripts/` using `CLAUDE_FILES`; no shared adapter or generic capability module
is changed.  Documentation directs a Claude session to capture its own native
receipt and invoke the contract locally for validation/bridge emission.

## Failure and Recovery

Provider failure, cancellation, hook loss, restart, and contradiction are
represented as receipt observations; they cannot close the run.  On restart,
unfinished receipt entries are `unknown`; a replacement receipt must use a new
attempt binding.  A contradicting phase creates a replan observation and marks
superseded phase output quarantined.  The contract reports validation failure
instead of inferring missing child or workflow state.

## Verification

Deterministic pytest covers each selected mode, both fallback directions,
identity binding, bounded hybrid delegation, rejection of fabricated evidence,
and package isolation.  Full local gates verify generated parity.  Native live
receipts require an exposed Claude Code Agent/Workflow surface and are not
claimed by deterministic fixtures.
