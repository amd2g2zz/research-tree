## Why

The Alpha2 OpenSpec task registry currently verifies JSON shape and dependency
cycles but does not verify whether a checked task group has verified
dependencies, whether task groups referenced by capability rows exist, or
whether an implementation issue owns the capability and task groups it claims.
That permits a structurally valid plan to report implementation progress that
cannot be justified by its prerequisites or evidence.

## What Changes

- Add an executable OpenSpec execution-governance registry for task-group
  lifecycle state, issue ownership, dependency semantics, evidence references,
  and explicit blocked/unavailable dispositions.
- Add a validator that rejects completed or verified task groups whose declared
  dependencies are not verified, missing group references, cycles, unknown
  lifecycle states, missing evidence, and issue/capability ownership conflicts.
- Repair the Alpha2 group registry and delivery matrix so groups 23--27 and
  issues #71--#87 have one resolvable authority and a non-cyclic dependency
  topology.
- Add deterministic valid and invalid fixtures, a generated governance report,
  and release-gate integration so structural OpenSpec validation is not treated
  as implementation proof.
- Preserve legacy and unavailable evidence as explicit non-verified states;
  no task is auto-promoted by a green structural check.

## Capabilities

### New Capabilities

- `openspec-execution-governance`: Defines dependency-aware task lifecycle,
  evidence requirements, issue-to-capability ownership, and release-facing
  validation for Alpha2 delivery planning.

### Modified Capabilities

None. The repository has no canonical OpenSpec specification directory yet;
the Alpha2 umbrella change remains a planning artifact and is not treated as a
completed capability implementation.

## Impact

- Adds a versioned governance registry, validator, fixtures, and report under
  the repository source tree.
- Updates Alpha2 task execution and delivery-matrix registries and the #67
  release checklist.
- Adds a required local and CI validation command before an Alpha2 task group,
  implementation issue, or release manifest can be marked verified.
