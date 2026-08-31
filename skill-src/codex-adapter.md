## Codex CLI runtime adapter

The SKILL body carries the activation state machine, protocols 1-6, and the
goal model; this adapter adds only Codex CLI host differences and never
duplicates a SKILL protocol.

### Activation probe
`research-tree-activation-contract:v1:codex`
Follow `references/skill-activation.md`: only exact `$research-tree activation-probe v1 <correlation-id>` plus matching app-server typed `skill` input may return only `research-tree-activation:v1:codex:<correlation-id>` without tools; other text, paths, or links are `activation_unverified`.

### Host conventions

- Read `references/codex-cli-compatibility.md` before host-specific alignment
  and `references/codex-native-orchestration.md` before repository execution,
  delegation, compaction, or recovery.
- Codex may expose the experimental `request_user_input` app-server request:
  use it only for a rare discrete decision after open-ended intent guidance
  and before strategy handoff. Do not assume it exists in a Skill shell or a
  non-interactive `codex exec` run; use ordinary dialogue when it is absent.
- After strategy handoff, map the active plan-to-execute wave onto Codex
  update_plan, parallel tool calls, and collaboration subagents when exposed.
  The plan UI is a session mirror; persist the Living Brief, execution state,
  evidence ledger, and next wave in the writable workspace before delegation
  or compaction. Dispatch independent agents concurrently, continue
  coordinator work while they run, and call `wait` only when no useful local
  work remains; verify artifacts and sources before accepting a subagent
  summary.
- Treat applicable AGENTS.md files as scoped execution constraints. After a
  resume, fork, or context compaction, reload the workspace checkpoint and
  re-check external side effects before retrying unknown work.
- After handoff, use `scripts/native_execution_adapter.py` with host argument
  `codex` for atomic task attempts, crash recovery, Finding Pack validation,
  and completion checks when Python is available; this executable state is
  authoritative over the visible plan, and a failed integrity check never
  becomes completion.
- In source-checkout development, record each source range with
  `context-record`, inspect its `context-receipt` before sending more
  context, keep unchanged rereads visible as `cached` or `replayed`, and
  keep active run outputs excluded until `context-seal` binds their digest.
  A `budget_exceeded` receipt is resumable but remains `unknown`, never
  completion.
- Use the stable lifecycle sequence `research-tree install`,
  `research-tree doctor`, `research-tree run`, `research-tree resume`,
  `research-tree status`, and `research-tree verify`
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts. Pass the ordinary workspace plus
  plain-language outcome, scope, authority, and success oracle; never
  construct HostEvent or SQLite inputs. A `prepared` or
  `verification_pending` receipt is fail-closed and never grants completion
  authority.
- Before mapping ready actions to collaboration, run `probe-host` with the
  surfaces exposed in the current session, bind the wave with
  `project-workflow`, and use `reconcile-host` after interruption before
  retrying unknown children. Partial, denied, or failed collaboration falls
  back to `coordinator-dispatch-v1` and never turns update_plan completion
  into canonical completion.

### Slot-only dispatch (Codex)

Dispatch only after explicit handoff. Give each worker only the Decision Slot, its source boundary, stop condition, and Finding Pack schema.
A worker MUST NOT receive the strategy projection digest, primary goal text, or other slots.
Codex collaboration children map to slots one-to-one; verify returned
Finding Packs against the slot's closure oracle before ingestion, and never
turn update_plan completion into slot closure.

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
