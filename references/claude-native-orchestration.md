# Claude Code Native Orchestration

Use this reference only under Claude Code. It maps `research-tree` execution
onto Claude Code 2.1.221 capabilities while remaining safe on narrower Agent
SDK and non-interactive surfaces.

## Preflight and project context

- Inspect the active tools. `AskUserQuestion`, Agent/Task tools, teams,
  background execution, browser/search, and task lists are session-dependent.
- Read applicable `CLAUDE.md` project instructions before repository work.
- Host permission mode, allowed/disallowed tools, network access, and workspace
  trust remain authoritative after the autonomy handoff.
- Do not start a nested `claude` CLI process to imitate an Agent tool. Outer
  CLI session management and in-session agent delegation are different layers.

In non-interactive `claude -p` or SDK execution without `AskUserQuestion`, run
bounded reconnaissance and persist a provisional intent rewrite, assumptions,
authority, and completion oracle. If safe defaults resolve the remaining
choices, hand off internally and continue; never exit with only questions or a
Blind-Spot Packet. Stop only for a permission, feasibility, or consequential
preference that cannot be responsibly inferred.

For a required external claim, try at most two materially different queries per
available backend, then change evidence class: native WebSearch, WebFetch of a
known official URL, configured documentation/search MCP, repository source, and
local vendored documentation. Record failures and never silently lower the
source standard.

## Task graph and agent selection

Mirror the current execution wave in the native task list when exposed, but
keep the durable strategy, attempts, evidence ledger, Insight Digest, and next
wave in workspace artifacts. A task-list UI or auto-memory is not the research
ledger.

Mirror adapter states consistently: `pending` is pending, `running` is
in-progress, and only `completed` plus `verified: true` is completed. Represent
`failed` and `unknown` as pending follow-up work with the attempt disposition in
its description; never show them as complete.

Choose the native worker shape by dependency:

- use parallel tool calls for independent deterministic reads;
- use isolated leaf agents for disjoint landscape, deep-dive, adversarial, and
  validation tasks;
- use a background agent only when the host exposes background execution and
  the parent has useful coordinator work to continue; and
- use an agent team only when at least two workers must exchange discoveries or
  debate a live contradiction. Tear the team down after that dependency closes.

Launch independent agents together rather than one per turn. Each receives the
Decision Slot, phase, source boundary, search variations, stop condition,
required output language, absolute artifact path, and Finding Pack schema.
Agents do not ask the requester, draft the final report, edit shared ledgers, or
spawn further workers unless the selected team topology explicitly requires a
single bounded peer exchange.

Custom project agents, when present, should specialize by epistemic role rather
than topic: scout, adversary, and validator. Prefer inherited model selection
unless evidence quality demonstrably needs a different model. Restrict tools
only when the task remains achievable with that restriction.

## Executable state adapter

After strategy handoff, initialize and advance durable state with the bundled
adapter:

```bash
python "<skill-dir>/scripts/native_execution_adapter.py" --host claude --workspace . init --run-id <run-id> --handoff .research-tree-alignment/<alignment-run>/handoff.json
python "<skill-dir>/scripts/native_execution_adapter.py" --host claude --workspace . add-task --run-id <run-id> --task-id <task-id> --decision-slot <slot> --phase landscape --artifact <finding.json>
python "<skill-dir>/scripts/native_execution_adapter.py" --host claude --workspace . start --run-id <run-id> --task-id <task-id> --worker-id <agent-id>
python "<skill-dir>/scripts/native_execution_adapter.py" --host claude --workspace . finish --run-id <run-id> --task-id <task-id> --result submitted
python "<skill-dir>/scripts/native_execution_adapter.py" --host claude --workspace . verify --run-id <run-id> --task-id <task-id> --reviewer-id coordinator --checked-anchor <opened-ref> --review-note <evidence-check>
python "<skill-dir>/scripts/native_execution_adapter.py" --host claude --workspace . status --run-id <run-id>
```

Resolve `<skill-dir>` from `${CLAUDE_SKILL_DIR}` when present or the injected
Skill path, never from the task workspace. `init` requires the persisted,
digest-confirmed handoff and copies its Decision Slots, authority, scope, and
success oracles into durable execution state. `add-task` rejects slots absent
from that handoff. Add dependencies with `--depends-on`
and give each worker the `attempt_id` returned by `start`. Run `recover` after a
crash, uncertain resume, or integrity error. It reopens corrupt artifacts and
their executed dependents so invalid evidence cannot release new work. `finish`
records a schema-valid submission; only the
parent's evidence review followed by `verify` releases dependent work. The
parent repeats `--checked-anchor` for every observation anchor it inspected. The
adapter hashes accepted artifacts, and `complete` fails while any task or
integrity check remains open. Mirror these transitions into the native task
list rather than updating two independent truths.
The parent serializes mutating adapter commands; parallel agents write only
their separate Finding Pack paths.

## Coordinator and verification

While agents run, the parent inspects uncovered repository surfaces, checks
source applicability, deduplicates claims, and prepares contradiction tests. Do
not poll background agents. Retrieve results after the host reports completion.

A child message is not evidence. Read its artifact, open decisive sources,
inspect raw commands/results, distinguish fact from inference, and record
counterevidence. The parent alone updates shared ledgers and produces the
Technical Research Package and Human Research Report.

## Long-horizon recovery

Persist a restart packet before delegation, `PreCompact`, and every meaningful
turn boundary. It contains the active strategy revision, task attempts,
artifact paths, open contradictions, completion oracle, and next wave.

Claude Code can continue or resume persisted sessions and can fork a resumed
session. These restore conversation context, not external execution truth. On
recovery, mark unfinished agent/process attempts `unknown`, inspect workspace
artifacts and `claude agents --json` when available, then ingest or retry with a
new attempt ID. Auto-memory may recover durable preferences or procedures, but
must not be the only copy of current task progress.

Use worktrees for concurrent implementation that could produce file conflicts,
not for read-only research by default. A background CLI session is an operator
choice; the in-session Skill must not launch one recursively.

## Hooks

Claude hooks load at session start. Relevant events include `SessionStart`,
`SessionEnd`, `UserPromptSubmit`, `SubagentStop`, `PreCompact`, `PostToolUse`,
and `Stop`. Use `${CLAUDE_PLUGIN_ROOT}` only in plugin hooks; repository settings
do not imply that variable exists.

Hooks may observe lifecycle or remind the agent to persist a checkpoint. A Stop
or SubagentStop gate must be bounded, reentrancy-safe, and based on an explicit
completion oracle. Never store prompts, child summaries, transcript content,
tool inputs, secrets, or research evidence in hook logs.
