## Codex CLI runtime adapter

### Activation probe
`research-tree-activation-contract:v1:codex`
Follow `references/skill-activation.md`: only exact `$research-tree activation-probe v1 <correlation-id>` plus matching app-server typed `skill` input may return only `research-tree-activation:v1:codex:<correlation-id>` without tools; other text, paths, or links are `activation_unverified`.

- Read `references/codex-cli-compatibility.md` before host-specific alignment.
  Before repository execution, delegation, compaction, or recovery, also read
  `references/codex-native-orchestration.md`.
- Codex may expose the experimental `request_user_input` app-server request;
  when exposed, use it only for a rare discrete decision after open-ended
  intent guidance and before the Research Strategy handoff. After the handoff,
  do not use it for ordinary
  research decisions; revise the strategy autonomously within the granted
  authority.
- Do not assume it exists in a Skill shell or non-interactive `codex exec` run;
  use ordinary dialogue when it is absent.
- After strategy handoff, map the active plan-to-execute wave onto Codex-native
  `update_plan`, parallel tool calls, and collaboration subagents when exposed.
  The plan UI is a session mirror; persist the Living Brief, execution state,
  evidence ledger, and next wave in the writable workspace before delegation or
  compaction.
- Give each subagent a disjoint Decision Slot and Finding Pack path. Dispatch
  independent agents concurrently, continue coordinator work while they run,
  and call `wait` only when no useful local work remains. Verify artifacts and
  sources before accepting a subagent summary.
- Treat applicable `AGENTS.md` files as scoped execution constraints. After a
  resume, fork, or context compaction, reload the workspace checkpoint and
  re-check external side effects before retrying unknown work.
- After handoff, use `scripts/native_execution_adapter.py` with host argument
  `codex` for atomic task attempts, crash recovery, Finding Pack validation, and
  completion checks when Python is available. This executable state is
  authoritative over the visible plan; never mark a run complete when its
  integrity check fails.
- In source-checkout development, record each source range through
  `context-record` and inspect its `context-receipt` before sending more context.
  Repeated unchanged ranges remain visible as `cached` or `replayed`; active run
  outputs are excluded until `context-seal` binds their digest. A
  `budget_exceeded` receipt is resumable but remains `unknown`, never completion.
- When the checkout runtime is available, use the stable lifecycle sequence
  `research-tree install`, `research-tree doctor`, `research-tree run`,
  `research-tree resume`, `research-tree status`, and `research-tree verify`.
  Pass the ordinary workspace plus plain-language outcome, scope, authority,
  and success oracle; never construct HostEvent or SQLite inputs. A `prepared`
  or `verification_pending` receipt is fail-closed and never grants completion
  authority.
- Before mapping ready actions to collaboration, run `probe-host` with the
  surfaces exposed in the current session. Use `project-workflow` to bind the
  concurrent wave to action, phase, child, permission, and checkpoint ids; use
  `reconcile-host` after interruption before retrying unknown children. Partial,
  denied, or failed collaboration falls back to `coordinator-dispatch-v1` and
  never turns `update_plan` completion into canonical completion.
