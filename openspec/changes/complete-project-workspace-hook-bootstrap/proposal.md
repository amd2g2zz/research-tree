## Why

The reverted first attempt created directories and configuration snippets but
left the legacy writable roots authoritative and did not prove an installed
hook could fire and recover the same project/run after restart.

## What Changes

- Establish one project/run workspace authority and a versioned manifest.
- Migrate the supported legacy local roots atomically into that workspace.
- Render dependency-free, installed hook launchers and probe them before a run
  can claim lifecycle hooks are available.
- Route native adapter and Hermes projection initialization through the same
  workspace identity and prove restart/cross-host recovery.

## Non-Goals

- Host task dispatch, interaction-state persistence, claim admission, and
  lifecycle completion authority remain owned by their respective issues.
