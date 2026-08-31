## Why

Research Tree already defines canonical scheduling, Host Events, source capture, and completion gates, but it does not yet negotiate or persist the native dynamic orchestration surfaces exposed by Claude Code, Codex, and Hermes. Without an executable adapter contract, host task lists and delegation mechanisms can drift from coordinator state, restart ambiguously, or be mistaken for completion authority.

## What Changes

- Add deterministic capability probes that distinguish available, unavailable, partial, denied, and failed host surfaces and bind the selected bounded fallback to a capability digest.
- Add non-authoritative native workflow projections for Claude Code dynamic phases, Codex concurrent ready tasks, and Hermes delegation with checkpoint-backed recovery.
- Translate native workflow lifecycle, replan, failure, cancellation, and reconciliation observations into canonical Host Events.
- Require bounded phase and child identity, durable checkpoint/resume state, stale-projection handling, and coordinator-only completion.
- Package host-specific executable adapters and operator guidance without emulating unavailable host APIs.

## Capabilities

### New Capabilities

- `host-native-orchestration`: Capability-negotiated, bounded native workflow projections and host-neutral fallback for Claude Code, Codex, and Hermes while the canonical coordinator retains state and completion authority.

### Modified Capabilities

None.

## Impact

- Runtime: new capability and native-workflow contract modules plus public exports.
- Host adapters: the dependency-free Codex/Claude adapter and a Hermes adapter gain capability probing, workflow projection, lifecycle event emission, and recovery commands.
- Protocol: existing HostEvent kinds expand to cover native workflow lifecycle and reconciliation observations.
- Packages and references: generated Codex, Claude Code, and Hermes packages expose only the adapters appropriate to each host.
- Tests and governance: group 26 receives executable evidence; package parity and the umbrella OpenSpec contract remain required gates.
