## Claude Code runtime adapter

The SKILL body carries the activation state machine, protocols 1-6, and the
goal model; this adapter adds only Claude Code host differences and never
duplicates a SKILL protocol.

### Activation probe
`research-tree-activation-contract:v1:claude`
Follow `references/skill-activation.md`: only exact `/research-tree activation-probe v1 <correlation-id>` or its plugin-qualified form may return only `research-tree-activation:v1:claude:<correlation-id>` without tools; paths and links are `activation_unverified`.

### Host conventions

- Resolve bundled resources from the active skill directory, including
  `${CLAUDE_SKILL_DIR}` when provided; never from the user's working
  directory. The installed package is read-only; artifacts live in the
  writable workspace.
- Read `references/claude-code-compatibility.md` before the first alignment
  or research action and before installation or hooks. Read
  `references/claude-native-orchestration.md` before handoff, delegation,
  compaction, or recovery.
- When the session exposes `AskUserQuestion`, use it only for a rare discrete
  decision after open-ended intent guidance and before strategy handoff;
  never assume the tool exists, and never call another host's tool merely
  because an example names it. In Claude Code, "I don't know" or a correction
  means teach and verify, never stop.
- After handoff, map ready waves onto Claude Code's native task list and
  Agent tool when exposed: launch independent agents together, continue
  coordinator work instead of polling, and use an agent team only when
  workers must debate. Dispatch an Agent only after `start`, bind the
  returned child identity with `bind-agent` (one identity never binds two
  attempts), and treat subagent messages as self-reports to verify against
  artifacts. The `PostToolUse:Agent` and `SubagentStop` hooks keep only
  sanitized opaque identity; unmatched identity stays `unknown_outcome`.
  Auto-memory and resume are secondary; the workspace checkpoint is
  authoritative after compaction or restart.
- After handoff, use `scripts/native_execution_adapter.py` with host argument
  `claude` for atomic task attempts, crash recovery, Finding Pack validation,
  and completion checks when Python is available; the native task list
  mirrors state, it never replaces it.
- In source-checkout development, use `context-record` and `context-receipt`
  to bound source reads; unchanged rereads stay `cached` or `replayed`, and
  active run outputs stay excluded until `context-seal` binds their digest. A
  `budget_exceeded` checkpoint permits only `context-resume` and remains
  `unknown`, not complete.
- Use the stable lifecycle sequence `research-tree install`,
  `research-tree doctor`, `research-tree run`, `research-tree resume`,
  `research-tree status`, and `research-tree verify`
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts. Supply ordinary workspace and plain-language
  authority inputs, never HostEvent or SQLite inputs; `prepared` and
  `verification_pending` are non-authoritative receipts with no completion
  authority.
- Before selecting dynamic phases, run `probe-host` with explicit session
  capability observations and build bounded projections with
  `project-workflow`. A failed or denied native surface selects
  `coordinator-dispatch-v1`; never infer availability from a task-list UI or
  reuse a stale capability digest.
- The installed package holds `SKILL.md`, bundled references and assets, and
  the dependency-free native execution adapter — not the repository Python
  runtime, hooks, builder, or evaluation corpus.

### Slot-only dispatch (Claude)

Dispatch only after explicit handoff. Give each worker only the Decision Slot, its source boundary, stop condition, and Finding Pack schema.
A worker MUST NOT receive the strategy projection digest, primary goal text, or other slots.
Map slots to Claude task-list waves and verify returned Finding Packs
against the slot's closure oracle before ingestion; the coordinator owns
synthesis, and workers never see each other's slots.

### Governance entry points

When interrupted use the correction protocol (`CorrectionEvent` kind
`correction` or `reopen` committed via `apply_correction`) and, for a
contradicted delivery, `apply_contradiction`
when the checkout runtime is available; otherwise persist the equivalent
intent in workspace artifacts. After delivery collect one of the
`ACCEPTANCE_DECISIONS` via `DeliveryAcceptance`; echo status from
`research-tree status` before any user-visible status message
when the checkout runtime is available; otherwise persist the equivalent
intent in workspace artifacts. The protocol semantics live in the SKILL
body; the host adds nothing.

### Source checkout development boundary

When Claude Code operates inside the `research-tree` checkout at the
requester's explicit request, the repository paths are: hooks/research_hook.py
(lifecycle hook launcher, run through `uv run`), src/research_tree/ (runtime,
edit via public API plus full suite), scripts/ (builder and staging tools —
after package-affecting changes run the package build check), and evaluation/
(development input only). Verify the checkout by its pyproject.toml, src/,
skill-src/, and packages/ markers, run `uv sync` first, and when the checkout
is unavailable report the missing development capability and continue with
the host-native workflow. Do not claim an installed package can execute these
files.

### Claude Code hooks

`research-tree-setup install` deploys fail-open lifecycle hooks into global
settings, preserving unrelated configuration; the hook returns immediately
without writing state when no project/run is active.
