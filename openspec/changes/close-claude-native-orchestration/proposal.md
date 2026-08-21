## Why

Claude Agent identities are visible in the native stream, but installed hooks
discard them and the adapter cannot bind a returned child identity to an active
canonical attempt. The capability contract also infers one generic native mode
instead of selecting Agent, Workflow, and hybrid independently.

## What Changes

- Preserve sanitized child, session, causation, task, and attempt identity in hooks.
- Bind one returned Claude agent identity to one active attempt and reject reuse.
- Add explicit Claude Agent, Workflow, and hybrid capability/mode validation.
- Keep native task/workflow status non-authoritative and fail closed on unmatched identity.
- Capture a live two-child Agent receipt and record Workflow/hybrid availability honestly.

## Non-Goals

No nested Claude CLI emulation, Codex/Hermes semantic change, or completion from
host status alone.
