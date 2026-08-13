## Context

The current Insight Digest writer emits a complete, versioned payload with
lineage, classification, delta, calibration, and policy fields. Its reader
still treats a four-field unversioned payload as valid by returning before the
rich-field checks. The active `insight-digest-v1.json` schema and example also
describe that older minimal shape, so they can reintroduce the retired reader
contract.

## Goals / Non-Goals

**Goals:**

- Admit one complete current Insight Digest shape at validation and scheduler
  ingress.
- Keep the deterministic writer and canonical digest behavior intact.
- Make active schemas, examples, requirements, and group 60 ownership express
  the same strict payload boundary.
- Prove canonical output is accepted and prior/minimal input is rejected
  before it can affect policy, replay, or delivery.

**Non-Goals:**

- Reading, migrating, rewriting, deleting, or otherwise acting on user-owned
  digest data.
- Adding a format version, alias, default inference, tolerant parser, warning
  path, read projection, or compatibility response.
- Modifying issue #171 or #168 evidence and registry entries.

## Decisions

### Require every field emitted by the current writer

Validation will require the complete field set emitted by
`synthesize_insights`, including its schema and producer markers. The allowed
key set will equal that required current set, retaining existing semantic
checks for schema version, lineage, and delta.

Alternative: require only `schema_version` and the existing rich subset.
Rejected because partial current-shaped payloads would retain a permissive
reader contract and could skip fields used for audit or replay.

### Reject before scheduler admission

The scheduler continues to call `validate_insight_digest` at its existing
boundary. Removing the early legacy return makes prior payloads fail before a
work portfolio can be created; no separate compatibility error path is
introduced.

Alternative: normalize old payloads at scheduler ingress. Rejected because it
would create an adapter and preserve the retired interface.

### Replace the active minimal schema and example

The active JSON schema and example will use the current writer's field set,
not a second minimal contract. The original OpenSpec change remains historical
design context but does not authorize a legacy runtime reader.

Alternative: leave the old schema as a documented historical reference.
Rejected because it is in an active schema registry and would remain a
published input contract.

## Risks / Trade-offs

- [Stored minimal digests no longer validate] -> Deliberate breaking cutover;
  the runtime does not inspect or mutate them.
- [Current tests or writers omit a field] -> Focused tests exercise the actual
  writer and fail deterministically at the shared validator.
- [Schema/runtime drift] -> The source and schema fields are asserted together
  in the focused regression suite.

## Migration Plan

1. Register group 60 / issue #174 and define its strict acceptance command.
2. Add canonical acceptance and minimal-rejection tests.
3. Remove the missing-version branch and replace active schema/example
   definitions with the current payload.
4. Validate the OpenSpec and governance contracts, commit source changes, then
   record source-bound evidence in a later handoff step.
5. Roll back only by reverting the release revision; do not restore a reader,
   adapter, or user-data action.

## Open Questions

None.
