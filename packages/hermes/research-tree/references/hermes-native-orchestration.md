# Hermes Native Orchestration

Use this reference only under Hermes Agent. It defines how `research-tree`
maps its plan-to-execute runtime onto Hermes v2026.8.3 capabilities.

## Capability preflight

Inspect the tools actually exposed in the current channel. Do not invent tool
arguments or assume every Hermes surface exposes every tool.

- Use `todo` for the current session's visible execution wave. It survives
  context compression but is not process-durable and is never the research
  ledger.
- Use writable workspace artifacts as the authoritative continuation state.
- Use `session_search` to recover relevant prior human-agent alignment. Treat
  recovered conversation as context, not current technical evidence.
- Use `memory` only for reusable user preferences or lessons that should apply
  across future runs. Do not store task progress, completed work, temporary
  TODOs, evidence ledgers, or report drafts in memory.
- Use `delegate_task` for independent reasoning or research. Use
  `execute_code` or ordinary file tools for deterministic transformations.
- Use Kanban tools, when exposed, as a mirror for task ownership and status;
  workspace state remains authoritative so the skill also works without them.

If a capability is absent, use the closest local fallback without weakening
the evidence or completion oracle.

## Wave dispatch

Compile each ready wave into disjoint leaf tasks. Dispatch up to the active
Hermes concurrency limit in one `delegate_task(tasks=[...])` call instead of
serial calls. Each task must include all context the child needs because child
contexts are isolated:

- exact decision slot and phase (`landscape`, `deep_dive`, `adversarial`, or
  `validation`);
- research question, source boundary, search variations, and stop condition;
- relevant Living Brief facts and explicit non-goals;
- required output language and absolute workspace artifact path;
- Finding Pack fields: atomic claims, evidence anchors, counterevidence,
  limitations, confidence, affected decision, and follow-up triggers; and
- a prohibition on user interaction, re-delegation, and final-report drafting.

Top-level Hermes delegations already run in the background. Do not pass a
`background` argument. Do not pass `toolsets` or a caller-selected
`max_iterations`; those are not model-facing controls in Hermes v2026.8.3.
Use leaf workers unless the configured spawn depth explicitly supports and
requires a nested orchestrator.

After dispatch, the parent should continue dependency-independent coordinator
work: inspect repository state, normalize the evidence ledger, test existing
claims, and prepare contradiction checks. Do not poll. Hermes delivers a
completion event when the batch finishes.

## Ingestion and verification

A child's final message is a self-report, not proof. For every returned task:

1. read the requested artifact and reject missing, empty, or schema-invalid
   output;
2. open decisive URLs or inspect cited repository paths and raw results;
3. separate supported claims from worker inference;
4. compare overlapping claims across workers and record contradictions;
5. update the Insight Digest and compile the next dependency-ready wave.

When diagnosis is needed, inspect `/agents` or `/tasks` and the append-only
delegation data under
`<hermes_home>/cache/delegation/live/<delegation_id>/`, including
`manifest.json` and `task-<n>.log`. These traces explain activity; they do not
replace source verification.

## Checkpoint and recovery

Persist the active strategy revision, task transitions, evidence ledger,
Insight Digest, and next ready wave before dispatch. Hermes persists completed
background notifications, but an in-flight child does not resume after a host
process crash. On restart:

1. recover the workspace checkpoint and relevant alignment with
   `session_search`;
2. mark any in-flight attempt `unknown`, never failed or completed by default;
3. inspect target artifacts and live delegation transcripts for side effects;
4. ingest valid completed output, otherwise issue a new attempt with a new ID;
5. record the supersession relationship to prevent duplicate evidence.

For work that must continue beyond the current process or session, and only
inside the granted autonomy envelope, create a one-shot or recurring `cronjob`
that explicitly attaches `research-tree`, uses an absolute workdir, reads the
authoritative checkpoint, executes one bounded drain/replan iteration, and
persists state before exit. A cron session must not create another cron job.

## Observability

The package's `scripts/hermes_runtime_hook.py` records sanitized session,
delegation, and subagent lifecycle metadata in
`.research-tree-hermes/events.jsonl`. Generate an absolute-path hook snippet
with:

```bash
python scripts/hermes_skill_adapter.py render-hooks
```

The hook never stores prompts, child summaries, tool arguments, secrets, or
research content. Hermes live transcripts remain the detailed debugging
surface. When ATOF/ATIF export is enabled, use it for aggregate execution and
cost analysis rather than duplicating telemetry in research artifacts.

For durable execution, use the Hermes-specific state adapter after the
alignment handoff:

```bash
python scripts/hermes_execution_adapter.py --workspace . init \
  --run-id <run-id> --handoff .research-tree-alignment/<alignment-run>/handoff.json
python scripts/hermes_execution_adapter.py --workspace . record-batch \
  --run-id <run-id> --batch-id wave-001 --status verified \
  --delegation-id <delegation-id> --finding findings/wave-001.json
python scripts/hermes_execution_adapter.py --workspace . recover --run-id <run-id>
python scripts/hermes_execution_adapter.py --workspace . prepare-delivery \
  --run-id <run-id> --technical-report technical-research-package.md \
  --human-report human-research-report.md
```

The adapter consumes Hermes worker-finished events supplied by the parent; it
does not call `delegate_task`. A verified wave and both report candidates can
move the host projection only to `delivery_pending`. The legacy `complete`
command is rejected; the canonical coordinator alone evaluates readiness,
acceptance, and completion.
