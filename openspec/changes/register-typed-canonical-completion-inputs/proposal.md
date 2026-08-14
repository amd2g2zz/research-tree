## Why

The completion path currently discovers the latest artifacts of several kinds
and trusts shallow status fields. Any caller that can use the generic ledger
append API can therefore construct valid-looking closure, insight, readiness,
or evaluation artifacts that appear eligible for a later completion decision.

This first #149 child establishes a single typed registration boundary before
the coordinator is allowed to consume those inputs.

## What Changes

- Add a transactionally registered canonical completion-input record for
  closure, insight, readiness, and evaluation evidence.
- **BREAKING**: generic `RunLedger.append_artifact()` artifacts cannot be
  registered as canonical completion inputs, even when their payloads resemble
  current artifacts.
- Require exact run, revision, lineage, currentness, quarantine, schema, and
  issuer validation before registration; make registration replay-safe.
- Migrate the dedicated closure, insight, readiness, and evaluation writers to
  register their validated output through the boundary.
- Register group 43 as planned, then record its source-bound acceptance only
  after the implementation commit.

## Capabilities

### New Capabilities

- `canonical-completion-input-registration`: typed, issuer-bound, replay-safe
  admission for closure, insight, readiness, and evaluation completion inputs.

### Modified Capabilities

- None.

## Impact

Affected areas are `run_ledger.py`, the dedicated closure/insight/readiness/
evaluation writers, coordinator completion-input lookup, their focused tests,
and Alpha2 group-43 governance registries. This slice deliberately excludes
completion-manifold resolution, delivery/acceptance, public CLI, and HostEvent
ingress.
