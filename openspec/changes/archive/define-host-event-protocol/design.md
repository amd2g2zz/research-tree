## Context

The coordinator already owns the SQLite lifecycle, but its current event
ingestion accepts arbitrary payloads and native adapters maintain filesystem
completion signals. Installed host packages do not carry the Python runtime,
so they must emit a validated transport envelope rather than open the ledger.

## Goals / Non-Goals

**Goals:**

- Validate one host-neutral envelope and deterministic semantic digest.
- Append accepted event plus non-terminal projection atomically and replay exact
  duplicates without changing canonical lifecycle state.
- Make Codex and Claude emit equivalent envelopes and remove local completion
  authority.
- Include focused pytest, Ruff lint, and Ruff format checks in each TDD slice.

**Non-Goals:**

- Hermes (#61), activation verification (#71), native workflow orchestration
  (#82), alignment (#59), policy (#58), or source checkpoints (#80).
- A new quarantine database; invalid events remain rejected or explicitly
  out-of-band according to the event disposition.

## Decisions

### Dependency-free typed validator

`host_events.py` will define immutable envelope and payload validators using
stdlib/dataclass code. The schema is documentation and interoperability; the
validator enforces event-specific bindings, digests, and sequence semantics.
Using a host package dependency was rejected because installed packages have
different runtimes.

### Coordinator atomic append boundary

`ResearchRunCoordinator.ingest_host_event` will validate before a single ledger
batch append of the host event and an attempt projection. It will check exact
run/attempt identity, expected revision, and monotonic sequence. It will never
call completion or readiness. A second store was rejected because it would
recreate split authority.

### Thin translators

Native adapters map provider traces and normalized paths to the same envelope;
they do not count tasks, inspect report headings/bytes, or write `complete`.
The shared helper remains in the authoring source and package generation owns
copies. Keeping a text fallback preserves host usability when native question
tools are unavailable.

## Risks / Trade-offs

- [Legacy callers expect local state files] -> preserve observation output where
  possible, but explicitly mark completion as non-authoritative.
- [Provider payload vocabularies differ] -> normalize only the shared event
  vocabulary and retain provider details inside typed payload fields.
- [Invalid events need diagnostics] -> return stable rejection/quarantine
  reasons without advancing the run revision or lifecycle state.
- [Generated packages drift] -> use `build_skill_packages.py --check` and a
  source/package semantic-digest fixture.

## Migration Plan

1. Add red envelope, ingestion, adapter, and parity tests.
2. Implement the validator and coordinator batch boundary.
3. Convert Codex/Claude translators and remove completion writes.
4. Rebuild/check packages and record group 8 evidence.

Rollback disables typed host-event cutover and retains append-only observations;
it must not restore adapter-local completion authority.
