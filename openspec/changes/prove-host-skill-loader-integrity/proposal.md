## Why

Any supported host package can be structurally valid while no durable record
proves which complete `SKILL.md` the host activated for a session. A later
rule can therefore be absent from the effective prompt without an observable
failure.

## What Changes

- Record one sanitized, digest-bound skill-load receipt for Codex, Claude, and
  Hermes session starts.
- Distinguish static package compatibility from verified loader integrity.
- Add deterministic start/middle/end mutation tests and host-specific loader
  probes, including an official-image Hermes probe when available.

## Non-goals

- Change alignment, coordinator, or research semantics.
- Patch any host runtime or treat a model response as loader proof.
