## Workspace Boundary

`project_id` names a stable semantic research topic. `run_id` names one execution
lineage below that topic; `session_id` names a host process segment. All three are
validated opaque identifiers. The initializer creates:

```text
.research-tree/projects/<project-id>/
  project.json
  runs/<run-id>/manifest.json
  runs/<run-id>/{alignment,plans,attempts,sessions,events,checkpoints,logs,deliveries}/
  exports/
```

The returned workspace descriptor is the sole path authority for this change.
It deliberately does not create a second runtime database or infer lifecycle
semantics.

## Hook Configuration

Codex merges owned hook entries into `.codex/hooks.json`; Claude merges owned
entries into `.claude/settings.json`. A marker on each generated command makes
replacement idempotent while preserving non-Research Tree entries. Writes use a
same-directory temporary file and replace; a failed multi-host bootstrap restores
the exact previous bytes (or removes a newly created file).

Hermes receives `.research-tree/projects/<project-id>/runs/<run-id>/hermes-home/config.yaml`
and the descriptor exposes `HERMES_HOME` for the caller. No path below the user
home is read or written.

## Lifecycle Records

Hook payloads may carry `project_id`, `run_id`, and `session_id`. When all are
present, the observer validates the initialized manifest and stores sanitized
event metadata below that run's `events/` directory. Without this descriptor,
legacy hook observation continues unchanged; it is not silently migrated.
