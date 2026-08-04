# Hermes Research Execution Phase

Load this file after strategy handoff or while recovering an autonomous run.
Also load `references/hermes-native-orchestration.md` before using delegation,
durable scheduling, or live delegation recovery.

## Compile the strategy

Represent the current strategy as one persisted recursive research state. Its
current frontier is a bounded dependency DAG, but later Finding Packs may grow
new successor actions. Each work item must contain:

- stable ID, decision slot, phase, dependencies, and owner;
- one bounded research question and explicit non-goals;
- source/search boundary and expected evidence class;
- absolute artifact path and Finding Pack contract;
- completion oracle, retry policy, and replan trigger.

Use phases `landscape`, `deep_dive`, `adversarial`, and `validation`. A broad
topic is not a work item. Split it until one worker can falsifiably complete it
without user interaction or final-report drafting.

## Drain loop

1. Reconcile the latest `research-tree-state`, task state, and artifact integrity.
2. Replay Finding Packs absent from `consumed_finding_ids` after a crash.
3. Select dependency-ready items by expected decision value, not worker self-score.
4. Dispatch independent items as one bounded wave.
5. Continue parent-only work: repository inspection, source normalization,
   contradiction preparation, and state maintenance.
6. Ingest only artifacts whose attempt ID and schema match the active task.
7. Verify decisive anchors independently.
8. Measure the actual evidence-ledger delta against the persisted baseline.
9. Grow, deduplicate, prune, or defer structured successor actions.
10. Persist the next tree revision and ready frontier before continuing.

Use task states `pending`, `running`, `submitted`, `completed`, `failed`, and
`unknown`. Submission never releases dependents. Only parent verification may
mark a task completed. A missing, changed, or stale artifact reopens the task
and any downstream result that depended on it.

## Finding Pack

Require atomic observations with claim, anchor, applicability, confidence, and
limitation; option effects; implementation implications; remaining
uncertainties; structured `research_continuations`; work item ID; research node
ID; decision slot; phase; and active attempt ID.
Schema validity is not evidence validity. Open important URLs, inspect cited
paths, reproduce calculations where proportionate, and compare overlapping
workers.

Historical Finding Packs are the initialization baseline and have zero
realized delta. A continuation records its kind, question, evidence trigger,
required evidence, oracle, and estimated cost. It does not assign information
gain or mutate the tree; the coordinator decides whether it becomes active.

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
