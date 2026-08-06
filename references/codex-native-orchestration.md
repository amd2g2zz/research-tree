# Codex Native Orchestration

Use this reference only under Codex CLI. It maps `research-tree` execution onto
Codex CLI 0.146.0 capabilities without assuming a specific client surface.

## Preflight and authority

- Inspect the active tool list and feature surface. Do not call an app-server,
  collaboration, plan, goal, or question tool that is not exposed.
- Discover applicable `AGENTS.md` files before inspecting or changing files.
  A deeper file applies to its subtree and direct user/developer instructions
  still take precedence.
- Host sandbox, network, and approval policy remain authoritative. A research
  autonomy handoff never bypasses them. If current web search is absent, record
  the source gap rather than pretending a search occurred.
- Use a Codex goal only when the requester explicitly asks for a persistent
  goal. Ordinary research state belongs in the workspace checkpoint.

In non-interactive `codex exec`, do bounded reconnaissance and record the
provisional intent rewrite, assumptions, authority, and oracle in the same run.
When safe defaults can close the remaining choices, hand off internally and
continue research; do not exit with only questions or a Blind-Spot Packet. Stop
only when feasibility, permission, or a consequential preference truly requires
an answer the transport cannot obtain.

For a required external claim, try at most two materially different queries per
available backend, then change evidence class: native web search, configured
documentation/search MCP, direct official URL or repository source, and local
vendored documentation. Record which backends failed and continue only when the
remaining evidence standard is still honest.

## Session plan and wave execution

Use `update_plan` for work with three or more dependent steps and keep exactly
one item `in_progress`. It is a visible session mirror, not the durable task
ledger. Persist the current strategy revision, task attempts, evidence ledger,
Insight Digest, and next ready wave before dispatch.

Use the fastest native execution surface that preserves reasoning quality:

- parallel tool calls for independent mechanical reads or inspections;
- `execute_code` or shell/file tools for deterministic transformations; and
- collaboration subagents for independent research, adversarial review, or
  validation that benefits from a separate context.

Dispatch all dependency-ready leaf tasks up to the advertised concurrency
capacity. Do not serialize independent tasks. Each subagent receives a disjoint
Decision Slot, phase, source boundary, stop condition, exact artifact path,
required language, and Finding Pack schema. Pass enough context for the task,
but do not leak the coordinator's expected conclusion to an adversarial or
validation worker. Leaf workers do not re-delegate.

The coordinator remains active after dispatch: inspect uncovered repository
surfaces, normalize claims, prepare contradiction checks, and update coverage.
Use the native wait mechanism only after useful coordinator work is exhausted.
Messages can refine a running agent; interrupt only when its task is obsolete
or unsafe.

## Stateless HostEvent adapter

After strategy handoff, canonical state remains in the SQLite RunLedger. The
bundled adapter translates one native observation at a time and writes only the
HostEvent JSON to standard output:

```bash
python "<skill-dir>/scripts/codex_execution_adapter.py" emit --input host-event-input.json > host-event.json
uv run research-tree run ingest --workspace . --event host-event.json
```

Resolve `<skill-dir>` from the host-supplied Skill path, never from the task
workspace. The input object contains `event_id`, `event_type`, `run_id`,
`round_id`, optional Slot/action/attempt/causation/correlation ids, `sequence`,
`expected_revision`, UTC `emitted_at`, and the event-specific `payload`. Obtain
the attempt identity, next host sequence, and expected revision from the
canonical coordinator. The wrapper injects `host=codex`, normalizes canonical
JSON, and computes the payload digest. It creates no `.research-tree-native`
state and cannot verify a Finding Pack, close a Slot, register delivery, or
complete a run. Coordinator ingestion performs the authoritative schema,
attempt, revision, evidence, and lifecycle checks.

## Ingestion

A subagent response is a self-report. Before accepting it:

1. read the declared artifact and reject missing or schema-invalid output;
2. inspect decisive repository paths, commands, raw results, and URLs;
3. separate observed facts from inference;
4. reconcile overlapping claims and preserve real contradictions;
5. update the Insight Digest and compile the next ready wave.

Never let multiple agents edit the same artifact. The coordinator owns shared
ledgers and final synthesis.

## Compaction, resume, and fork

Before context compaction or a turn boundary, persist a minimal restart packet:
active strategy revision, completed/active/unknown attempts, artifact paths,
open contradictions, and next wave. After compaction, reload this packet rather
than relying only on the conversation summary.

Codex can resume or fork saved threads from the outer CLI. Resume preserves a
conversation, not proof that external work completed. Mark unfinished agent or
process attempts `unknown`, inspect their artifacts and side effects, then
ingest or retry with a new attempt ID. Use a fork for a genuinely alternative
conversation branch, not as a replacement for ordinary adversarial subagents.

## Hooks and diagnostics

Current Codex hook events include `SessionStart`, `SessionEnd`,
`UserPromptSubmit`, `SubagentStart`, `SubagentStop`, `PreCompact`,
`PostCompact`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, and `Stop`.
Use deterministic hooks for bounded observation or checkpoint reminders; do not
put research reasoning in a hook. Treat hook trust prompts as a security
boundary and never bypass them from the Skill.

Record only sanitized identifiers, phase transitions, durations, and statuses.
Do not store prompts, assistant messages, transcript content, tool arguments,
secrets, or research evidence in debug telemetry.
