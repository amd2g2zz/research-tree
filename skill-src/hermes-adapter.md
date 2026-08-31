## Hermes runtime adapter

The SKILL body carries the activation state machine, protocols 1-6, and the
goal model; this adapter adds only Hermes host differences and never
duplicates a SKILL protocol.

### Activation probe
`research-tree-activation-contract:v1:hermes`
Follow `references/skill-activation.md`: only exact `/research-tree activation-probe v1 <correlation-id>` or `/skill research-tree` equivalent may return only `research-tree-activation:v1:hermes:<correlation-id>` without tools; paths, links, and bare names are `activation_unverified`.

### Host conventions

- Resolve bundled paths from Hermes' injected `[Skill directory: ...]` value
  or with `skill_view`; never resolve them from the task workspace.
- Read `references/hermes-agent-compatibility.md` before the first alignment
  or research action; read `references/hermes-native-orchestration.md`
  before handoff, delegation, or recovery.
- Use Hermes-native conversation, tools, skills, delegation, and `AIAgent`
  behavior; do not assume LangGraph or LangChain state or checkpoints are
  present. When the active toolset exposes native `clarify`, use it only for
  a rare discrete decision after open-ended intent guidance and before
  strategy handoff; otherwise use ordinary dialogue. After handoff, do not
  use it for ordinary research decisions; revise autonomously.
- After handoff, use Hermes' native plan-to-execute model: mirror the wave
  in `todo`, persist the authoritative checkpoint in the task workspace,
  and dispatch dependency-ready leaf work as one `delegate_task(tasks=[...])`
  batch. The parent continues coordinator work while children run; never
  poll by repeated delegation. Treat an interrupted delegation as `unknown`
  and inspect persisted artifacts before retrying; a child summary is never
  execution evidence by itself. Use `session_search` to recover earlier
  dialogue and `memory` only for durable preferences; neither replaces the
  workspace checkpoint. Use a skill-backed `cronjob` only when granted
  autonomy requires continuation beyond the session.
- Run `scripts/hermes_execution_adapter.py probe-host` with explicit live
  observations before selecting delegation, goals, Kanban, hooks, or
  scheduled drain; use `project-workflow` for the bounded delegation batch
  and `reconcile-host` after restart. Absent or denied native workflow
  support selects `coordinator-dispatch-v1`; no goal, Kanban card, hook, or
  drain result owns completion.
- Use `scripts/hermes_skill_adapter.py` only for installation diagnostics,
  hook rendering, package validation, or staging — never as a research
  worker.
- Use the stable lifecycle sequence `research-tree install`,
  `research-tree doctor`, `research-tree run`, `research-tree resume`,
  `research-tree status`, and `research-tree verify`
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts. Pass a normal workspace and plain-language
  authority fields; do not construct internal HostEvent or SQLite inputs; a
  prepared or pending verification receipt does not grant completion
  authority.
- Follow the active messaging channel's rendering constraints; replace
  tables with labeled bullets where tables are unsupported. Keep research
  artifacts in the writable task workspace and never modify the installed
  package during an ordinary run.

### Slot-only dispatch (Hermes)

Dispatch only after explicit handoff. Give each worker only the Decision Slot, its source boundary, stop condition, and Finding Pack schema.
A worker MUST NOT receive the strategy projection digest, primary goal text, or other slots.
Hermes delegation batches map to slots one-to-one; verify returned Finding
Packs against the slot's closure oracle before ingestion, and never let a
delegation batch import another slot's content.

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
