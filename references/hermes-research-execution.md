# Hermes Research Execution Phase

Load this file after strategy handoff or while recovering an autonomous run.
Also load `references/hermes-native-orchestration.md` before using delegation,
durable scheduling, or live delegation recovery.

## Compile the strategy

Represent the current strategy as one versioned dependency DAG. Each work item
must contain:

- stable ID, decision slot, phase, dependencies, and owner;
- one bounded research question and explicit non-goals;
- source/search boundary and expected evidence class;
- absolute artifact path and Finding Pack contract;
- completion oracle, retry policy, and replan trigger.

Use phases `landscape`, `deep_dive`, `adversarial`, and `validation`. A broad
topic is not a work item. Split it until one worker can falsifiably complete it
without user interaction or final-report drafting.

## Drain loop

1. Reconcile persisted task state and artifact integrity.
2. Select dependency-ready items by information gain and decision impact.
3. Dispatch independent items as one bounded wave.
4. Continue parent-only work: repository inspection, source normalization,
   contradiction preparation, and state maintenance.
5. Ingest only artifacts whose attempt ID and schema match the active task.
6. Verify decisive anchors independently.
7. Update evidence coverage, contradictions, Insight Digest, and strategy.
8. Persist the next ready wave before continuing or returning.

Use task states `pending`, `running`, `submitted`, `completed`, `failed`, and
`unknown`. Submission never releases dependents. Only parent verification may
mark a task completed. A missing, changed, or stale artifact reopens the task
and any downstream result that depended on it.

## Finding Pack

Require atomic observations with claim, anchor, applicability, confidence, and
limitation; option effects; implementation implications; remaining
uncertainties; work item ID; decision slot; phase; and active attempt ID.
Schema validity is not evidence validity. Open important URLs, inspect cited
paths, reproduce calculations where proportionate, and compare overlapping
workers.

## Insight mechanism

After each wave, synthesize rather than concatenate. For every meaningful
cross-source pattern record:

- observation and supporting claims;
- mechanism or causal explanation;
- consequence for a decision slot;
- novelty versus the current brief;
- confidence and falsifier;
- implementation implication or next experiment.

Promote an insight only when it changes a decision, research priority,
architecture, validation plan, or risk boundary. Record negative insights and
contradictions; do not average disagreement into vague prose.

## Dynamic revision

Intent understanding remains active throughout the round. If evidence changes
the desired outcome, scope, premise, safety boundary, or success oracle, create
a successor brief and tree revision and continue autonomously inside the
existing authority. Re-enter human collaboration only when the change requires
new authority or a consequential preference the agent cannot infer safely.

## Convergence

Stop only when all required decision slots meet their evidence thresholds,
adversarial checks have run on decisive claims, unresolved contradictions are
bounded, implementation consequences are concrete, and the delivery gates can
be evaluated. Exhausting a time slice, context window, provider retry budget,
or worker wave means checkpoint and resume, not completion.
