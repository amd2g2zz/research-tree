## Why

Research topics currently split their durable local material across host-specific
roots. A session restart or host change can therefore create unrelated writable
state. Project hooks are templates only, so a capability declaration does not
prove a project-local hook was configured.

## What Changes

- Add a project/run workspace initializer under `.research-tree/projects/`.
- Add atomic, idempotent project-local Codex and Claude hook configuration.
- Add a project-local Hermes home/configuration and launch environment.
- Route lifecycle records into the selected project/run/session event root.

## Non-Goals

- No interaction-state reducer, Recall policy, claim admission, or host task
  dispatch.
- No user-global host configuration mutation and no completion authority.

## Acceptance Evidence

Focused tests must prove idempotence, unrelated configuration preservation,
rollback after a failed configuration write, per-project event isolation, and
Hermes global-home preservation. All mutable run material stays under ignored
`.research-tree/`.
