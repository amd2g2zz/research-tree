# Debug Tracing

Debug tracing is a fail-open, opt-in side channel of the setup-managed
lifecycle hook. It exists for bounded diagnosis only; it is not part of a
research workflow and is never a source of completion authority.

## What it does

When the lifecycle hook runs with `--debug`, each successful `recorded`
observation appends one sanitized JSON event under
`.research-tree-debug/events/` with:

- `host`: the hook host (`codex`, `claude`, or `hermes`)
- `phase`: `lifecycle_observed`
- `status`: `completed`
- `codes`: bounded reason codes such as `event:SessionStart`
- optional `run_id` when provided through hook arguments

Records carry no prompts, model responses, tool inputs, URLs, repository
contents, secrets, personal data, or environment variables. Files are written
atomically with owner-only permissions where supported; the directory is
ignored by Git.

## Run it

Only when diagnosing hook behavior from a source checkout:

~~~bash
uv run --locked research-tree-hook --host claude --event SessionStart --debug
~~~

It remains fail-open. A trace failure is swallowed like any other hook
failure: the hook's response to the host never changes and no session is
blocked. In debug mode, a setup failure is written to stderr when the host
exposes stderr.
