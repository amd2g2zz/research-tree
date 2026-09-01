## Context

The canonical strategy-projection schema already requires
`preference_influences`, but `StrategyProjection.create` supplies an empty
tuple when the caller omits it and `from_dict` rebuilds an old payload with a
separate digest path. Those branches keep a prior payload shape alive after
the writer changed. The current-only cutover treats that shape as invalid
instead of adapting it.

## Goals / Non-Goals

**Goals:**

- Accept exactly one complete projection schema in construction and loading.
- Preserve deterministic canonical digest validation for current payloads.
- Keep completed delivery evidence as history while retiring the active
  compatibility requirement that mandated old reads.
- Register issue #173 as a source-bound Alpha2 delivery group before code
  verification.

**Non-Goals:**

- Reading, rewriting, migrating, deleting, or otherwise acting on
  user-owned projection data.
- Bumping the projection schema version or adding an alternate format.
- Adding aliases, default inference, field coercion, a warning path, a
  rejection adapter, or a user-facing migration command.

## Decisions

### Enforce the complete writer shape at both boundaries

`create` will require `preference_influences` just as it requires every other
canonical field. `from_dict` will require the exact top-level and nested
display payload shape, construct one canonical value, and compare the stored
payload and digests to that value. A missing field produces the existing
stable `projection fields do not match schema` diagnostic.

Alternative: keep the default in `create` while tightening only `from_dict`.
Rejected because the direct constructor would remain a legacy minimal writer
and eventually recreate a payload which the reader rejects.

### Archive, rather than rewrite, completed legacy-read planning

The completed preference-profile change is the only active requirement that
orders compatibility reads for this exact payload. Its completed artifacts and
receipts move intact to `openspec/changes/archive/`; active registries point
only to the current retirement change. Historical source remains auditable but
cannot govern present runtime behavior.

Alternative: edit the completed change in place. Rejected because an active
completed change would still compete with the current-only contract.

### Use absence and rejection tests as the cutover proof

Focused tests construct a canonical payload and assert round-trip success,
then derive missing-field and prior minimal payloads to assert a stable
rejection. Tests also ensure no source branch or active document revives the
reader fallback.

## Risks / Trade-offs

- [Stored prior projections cannot load] -> Deliberate breaking cutover; Git
  history preserves removed source, while the runtime never touches user data.
- [Current writers omit the field] -> Focused fixtures and all direct call
  sites are updated before deletion, causing early deterministic failures.
- [Registry ownership drifts] -> Group 59 is planned before implementation,
  then receives a source-bound receipt after the final rebase.

## Migration Plan

1. Register the strict reader requirement and planned group 59.
2. Add failing tests for missing-field construction and old serialized shapes.
3. Remove both fallback branches and archive the completed legacy-read
   contract without syncing it into active specifications.
4. Run focused and broader checks; commit source before recording a group-59
   receipt after rebasing on current `origin/dev`.
5. Roll back only by reverting the release revision; do not restore a runtime
   reader, adapter, or data action.

## Open Questions

None. Issue #173 fixes the required canonical payload and no-compatibility
boundary.
