## Why

The existing low-trust RunStore importer preserves one Alpha1 source, but
alignment/native/Hermes host state can still be mistaken for a writable
completion path. Alpha2 needs an explicit, non-destructive cutover boundary.

## What Changes

- Add a deterministic Alpha1 migration inventory and read-only compatibility
  projection for native and Hermes checkpoint state.
- Diagnose unsupported, stale, duplicate, and corrupt legacy state without
  importing completion authority or changing legacy files.
- Permit retirement of legacy writable completion paths only with a registered
  passing release gate.

## Non-Goals

- Deleting, moving, or rewriting user-owned Alpha1 directories.
- Treating historical validation, closure, delivery, or completion data as
  Alpha2 readiness or completion.
