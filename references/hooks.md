# Repository-Local Hooks

`hooks/research_hook.py` is an optional lifecycle observer for this checkout.
It is deliberately not a global installation and does not replace the
orchestrator, worker protocol, or research DAG.

The supplied JSON files are templates only:

- `hooks/claude-code.settings.template.json` contains the direct event entries
  for this repository's `.claude/settings.json`.
- `hooks/codex.hooks.template.json` is a repository-local `.codex/hooks.json`
  file for Codex.

Activate either template only after `uv sync --locked`, from the repository
root. Their command strings are static; neither template interpolates stdin,
the prompt, a transcript path, or an environment-derived workspace path.

## Lifecycle behavior

`SessionStart` records one small event only after an existing
`research_drift/research_state.json` is present. `Stop` first performs an
in-process, read-only `ResearchOrchestrator.plan()` and records only separate
worker and coordinator task counts and roles. It never writes `worker_batch.json`, executes a worker,
submits a command, searches, or changes the research DAG.

Each event is an independently created JSON file in
`research_drift/hook_events/`; this avoids concurrent JSONL append races. The
record contains the event type, action, timestamp, repository-relative
workspace, and (for plan mode) a minimal plan summary. It does not persist the
raw prompt, tool input, transcript path, model, or session ID.

## Safety boundary

The handler reads at most 64 KiB of UTF-8 JSON from stdin. It requires an
absolute reported `cwd`, verifies both that value and the process working
directory resolve beneath the checked-in repository root, and ignores a
re-entrant `Stop` event. It does not call `subprocess`, a shell, or a network
client. Invalid or out-of-scope input is ignored with a non-blocking
`{"continue": true}` response, because these hooks are observers rather than
permission gates.

The templates assume Claude Code or Codex is started at this repository root.
They are not suitable for pointing a checked-out skill at an arbitrary external
research directory. Keep the hook workspace inside the checkout, or use a
separately reviewed deployment adapter with an explicit trusted workspace root.

Claude Code hook settings and Codex project hook configuration are documented
by [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
and [Codex configuration](https://developers.openai.com/codex/config-reference/).
