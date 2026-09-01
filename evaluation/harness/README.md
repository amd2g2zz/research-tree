# Evaluation Entry Points

The governed public entry point is:

```text
uv run python scripts/check_evaluation_assets.py --public-alpha1
```

It validates the path registry and the public Alpha1 manifest without running
hidden oracles or writing output under tracked evaluation paths. Unit,
integration, black-box, cross-host, and expert-review command identities are
registered in `evaluation-paths-v1.json`; unavailable private components must be
reported as unavailable rather than inferred as passing.

The Issue #72 fixture is explicitly synthetic and non-historical:

```text
uv run python evaluation/harness/run_claude_glm_regression.py --expect-status unavailable
```

It evaluates deterministic control transitions but does not execute a live
Claude Code or GLM runtime. A missing GLM runtime produces a named
`unavailable` result and cannot establish parity or causal attribution.

## Host failure-injection matrix (issue #292 gate 7)

`host_matrix.py` + `run_host_matrix.py` orchestrate six failure scenarios
x three admitted hosts (`codex`, `claude`, `hermes`) and emit one canonical
receipt:

```text
uv run python evaluation/harness/run_host_matrix.py --workspace .research-tree/evaluation-runs/gate7 --result .research-tree/evaluation-runs/gate7/receipt.json
# subsets:
uv run python evaluation/harness/run_host_matrix.py --workspace W --result R --hosts claude --scenarios interruption,resume
```

Scenarios: `interruption`, `provider_error`, `stale_child`,
`artifact_tamper`, `resume`, `cross_workspace_isolation`. Each cell drives a
real runtime run to its injection point, injects through the runtime's
existing failure-handling path (host-event ingestion, real CAS byte mutation,
the run-bound launcher subprocess, the host-neutral CLI), observes the
disposition, and records: scenario, host, injection transport, cause,
expected vs observed canonical reason, false-completion and mutation flags,
and evidence. Receipts reuse the host-conformance result shape
(`schema_version`/`case_id`/`mode`/`status`/`cells`, cell `name` is
`<scenario>:<host>`), with per-cell provenance under a `matrix` key.

Receipts are written to the `--result` path; because cells execute real
runtime state, run them under the disposable evaluation root
(`.research-tree/evaluation-runs/`), never under tracked paths.

Live vs simulated vocabulary (also embedded in every receipt under
`matrix.live_vs_simulated`):

- Every cell is a **live runtime** execution: the whole
  setup -> inject -> observe chain runs real runtime code on real ledgers,
  files, subprocesses, and CLI entries. No runtime component is mocked.
- `cause` distinguishes the failure origin: `runtime-internal` (stale child,
  artifact tamper, cross-workspace isolation: the injected state is real),
  `synthesized-trigger` (interruption, provider error: an external cause is
  declared through the runtime's real declaration path), `runtime-cli`
  (resume, via the real CLI).
- `host_process_invoked` is `false` in every receipt: no third-party host
  product binary (Codex CLI, Claude Code, Hermes agent) is in the loop, and
  no cell may be cited as host-product-in-the-loop evidence.
- Per-host injectability asymmetry (recorded, not papered over): the
  run-bound launcher binds interrupted-child identity only for the
  Claude-style `SubagentStop` event name that codex and claude share. The
  hermes cell emits `subagent_stop`, so its launcher record carries no
  `binding_status`; the cell stays live at the runtime level (attempt-outcome
  classification plus coordinator rejection) and records the launcher
  limitation in `detail`.

