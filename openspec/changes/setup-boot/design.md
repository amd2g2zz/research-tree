# design — setup-boot

Provisioner and confirm gate are injected — the T0 core ships the idempotent
flow + readiness shape; the concrete CLI installs are #552's pi extension
mount + provider CLIs. Fresh-machine path: runSetup creates the workspace
(ledger migrations run inside), doctor verifies.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Silent global installs (the confirm gate is a product red line: 全局动作先问).
- Generic "setup failed" (every failed check names the provider and its install guidance).
- Non-idempotent setup (second run must be a no-op).
