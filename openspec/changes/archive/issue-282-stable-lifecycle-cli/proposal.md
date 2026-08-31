# Stable Host-Neutral Lifecycle CLI

## Why

The public `research-tree` command required callers to construct a typed
HostEvent JSON envelope and to know the canonical SQLite workspace layout.
That leaks storage concerns into installation and lifecycle operations, makes
clean-checkout diagnosis fragile, and gives no stable cross-host command
sequence.

## What Changes

- Publish six user-facing commands: `install`, `doctor`, `run`, `resume`,
  `status`, and `verify`.
- Return one versioned lifecycle JSON schema that always exposes the canonical
  authority revision and explicit readiness failure reasons.
- Create a durable lifecycle request from plain-language outcome, scope,
  authority, and success-oracle fields without accepting raw HostEvent or
  SQLite inputs.
- Keep verification fail-closed until aligned authority, oracle evidence, and
  an independent reviewer receipt exist; the CLI cannot complete a run.
- Restrict raw coordinator transport to an unadvertised, acknowledged internal
  contract and document the same lifecycle sequence in every generated host
  package.

## Non-goals

- Treating a project-local hook probe, static installation status, or a host
  transcript as completion authorization.
- Replacing the canonical coordinator, Finding Pack validation, or host-native
  execution adapters.

## Impact

- Affects the console entrypoint, documentation, generated host skill text,
  OpenSpec contract, and CLI/wheel/package regression coverage.
