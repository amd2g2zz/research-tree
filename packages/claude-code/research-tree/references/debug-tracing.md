# Debug Tracing

Use this reference only when the requester explicitly asks to diagnose Research
Tree behavior, or when `RESEARCH_TREE_DEBUG=1` is intentionally enabled. Debug
tracing is opt-in and writes only to a source checkout. It is not part of an
installed Skill package's normal workflow.

## What to record

Emit a phase event after each meaningful transition, not every model message:

| Phase | Status | When to emit |
| --- | --- | --- |
| `intake` | `started` | Context Pack accepted for inspection |
| `reconnaissance` | `completed` | Bounded inspection or search batch completed |
| `alignment_checkpoint` | `completed` | Goal, scope, authority, oracle, open decisions, and feasibility made visible |
| `alignment_blocked` | `blocked` | A high-impact decision prevents implementation |
| `research_started` | `started` | Alignment gate permits implementation-oriented research |
| `implementation_started` | `started` | Target edit, implementation artifact, or irreversible experiment begins |
| `worker_blocked` | `blocked` | A worker exhausted search, local inspection, and safe alternatives |
| `completed` or `aborted` | matching status | Work ends or is intentionally stopped |

Use `--code` only for bounded, non-sensitive reason codes such as
`missing-success-oracle`, `awaiting-authority`, `feasibility-indeterminate`,
or `target-edit-authorized`. Never put prompts, responses, URLs, repository
contents, secrets, personal data, environment variables, tool input, or free
form notes in a trace.

## Source-checkout commands

Only when `research-tree-debug` is available from the source checkout, emit a
record with the active host name:

```bash
uv run --locked research-tree-debug emit \
  --host codex --phase alignment_blocked --status blocked \
  --code missing-success-oracle
```

Inspect a compact chronological summary with:

```bash
uv run --locked research-tree-debug summary --limit 50
```

Trace files are atomically written under `.research-tree-debug/events/` with
owner-only file permissions where supported. The directory is ignored by Git.
Do not enable a lifecycle hook merely to collect ordinary research logs.

## Lifecycle hook debug mode

The optional lifecycle hook can also emit a `lifecycle_observed` event for each
host start/stop event. Add `--debug` to its existing command only while
diagnosing hook setup, for example:

```bash
uv run --locked research-tree-hook --host claude --event SessionStart --debug
```

It remains fail-open. In debug mode, a setup failure is written to stderr when
the host exposes stderr; it never changes the host's hook response or blocks a
session.
