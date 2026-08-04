---
name: research-tree
description: "Use when explicit deep technical research must align a vague or evolving problem with the requester, then run autonomous evidence-driven research and deliver an actionable Technical Research Package plus a concise Human Brief."
---

# research-tree

## Outcome

Turn a research request into two co-primary deliverables:

1. an evidence-bearing Technical Research Package detailed enough to drive
   implementation; and
2. a short Human Brief that the requester can understand, challenge, and use.

The requester and agent co-evolve the intent before strategy handoff. The
requester controls outcomes, preferences, and authority, but both human and
agent technical claims remain falsifiable. After handoff, the agent owns the
long-horizon research inside the agreed autonomy envelope.

## Progressive loading

Hermes injects this file into the model request in full. Keep the first turn
small; never eagerly load every supporting file.

- Resolve files from Hermes' injected `[Skill directory: ...]` value or with
  `skill_view`; never resolve them from the task workspace.
- Read `references/hermes-alignment.md` when intent is vague, disputed, or not
  yet at strategy equilibrium. It contains the detailed mutual-alignment loop.
- Read `references/hermes-research-execution.md` only after strategy handoff or
  when recovering an autonomous run.
- Read `references/hermes-delivery.md` only when synthesizing or auditing final
  deliverables. At that phase, use `assets/brief-template.md`,
  `assets/research-strategy-template.md`,
  `assets/technical-research-package-template.md`, and
  `assets/human-brief-template.md` for persisted artifacts rather than pasting
  their schemas into chat.
- Read `references/hermes-native-orchestration.md` only before delegation,
  recovery, or durable scheduling.
- Read `references/hermes-agent-compatibility.md` only for host capability,
  installation, or rendering questions.
- Read `references/blueprint-generation-research.md` only when revising a
  Blueprint Target or Decision Map, and `references/product-contracts.md` only
  when exact persisted schemas matter.
- Read `references/debug-tracing.md` only for explicit behavior diagnosis.

Do not load `references/research-quality-playbook.md` in Hermes; the three
Hermes phase references are its context-bounded operational form.

## Phase 1: mutual alignment

Unless the requester explicitly says to skip discussion and execute directly,
treat the initial request as materially incomplete. A repository plus a
question still requires understanding the desired outcome, users, boundary,
quality bar, environment, authority, and success oracle.

Before asking detailed questions:

1. inspect supplied artifacts, repository state, and the smallest useful set
   of external sources;
2. mirror the current reading as a hypothesis, including one assumption,
   blind spot, or counterargument;
3. add knowledge the requester did not yet have and explain why it changes the
   decision; and
4. invite one open-ended correction or elaboration in the requester's own
   words.

Keep each interactive response under 1000 characters. A turn must contain
progress or teaching; never return a question-only questionnaire. Do not use
multiple-choice menus as the default. Use native `clarify` only for a rare,
bounded decision after the distinction is understood and only when the active
Hermes surface exposes it. Otherwise use ordinary dialogue.

Treat vague language, "I don't know", confusion, and corrections as difficulty
signals. Search, inspect, or run a safe spike; then explain one useful
distinction and ask one guided reflection. Do not invent requirements or stop
because the requester lacks vocabulary.

Maintain a Living Brief and claim ledger in the writable task workspace.
Persist structured belief deltas and decisions, not full conversation
transcripts or secrets. User feedback that corrects the agent changes the
brief; it is not merely a report-edit request.

Before handoff, establish an Alignment Checkpoint containing goal and
deliverables, scope and non-goals, authority and environment, success oracle,
evidence standard, feasibility, and unresolved high-impact decisions. The
strategy handoff occurs at decision equilibrium: visible mutual cognition
change, supported feasibility, an actionable oracle, and no unresolved
decision that could materially redirect the work. "Okay" or "continue" alone
is not alignment evidence.

For the full algorithm and equilibrium tests, load
`references/hermes-alignment.md`.

## Phase 2: autonomous plan-to-execute research

At handoff, state the Autonomy envelope after strategy handoff:

- autonomous choices: research, search, experiments, delegation, scheduling,
  and recoverable strategy revisions inside granted authority;
- hard stops: insufficient authority or safety boundary, unavailable required
  capability, or an honestly unevaluable completion oracle;
- continuation state: brief revision, one active tree revision, Decision Map,
  task state, evidence ledger, Insight Digest, and next ready wave;
- completion oracle and evidence threshold; and
- retry/replan policy without silent goal downgrade.

This work is cost-tolerant unless the requester supplies a monetary cap. Host
time slices, context, concurrency, and tool limits are checkpoint boundaries,
not reasons to declare the research complete or infeasible.

Compile the strategy into a dependency DAG of bounded work items. Do not hand a broad track to
one worker and do not let workers re-delegate unless a
deliberate nested-orchestrator design and host depth allow it. Every item needs
one decision slot, evidence target, source boundary, artifact path, completion
oracle, and replan trigger.

Execute ready items in waves. Use Hermes-native `todo` only as a visible
session mirror; workspace state is authoritative. When `delegate_task` exists,
batch independent leaf tasks in one `delegate_task(tasks=[...])` call and keep
doing coordinator work while they run. Verify source anchors and artifacts;
never treat a child summary as proof.

After every wave:

1. ingest atomic claims with provenance, applicability, confidence, limits,
   and counterevidence;
2. update contradictions and the Insight Digest;
3. test whether evidence changes intent, strategy, scope, or success criteria;
4. replace the active tree when premises change and record why; and
5. persist continuation state before another dispatch or return.

Intent understanding remains active throughout the round; it is not a one-time
pre-research gate.

Research recursively until the evidence coverage and decision slots satisfy
the completion oracle. A tree, source list, recommendations list, or compiled
brief is not completion. A worker may report a blocker only after available
search, local inspection, and safe alternatives have been attempted.

Load `references/hermes-research-execution.md` for task states, Finding Packs,
insight generation, contradiction handling, recovery, and convergence gates.

## Phase 3: delivery

Produce the Technical Research Package first. It must include the evolved
problem framing, method and source boundaries, findings with citations,
counterevidence, resolved and open contradictions, decisions and rejected
alternatives, implementation consequences, validation plan, risks,
uncertainty, and exact artifact status. Distinguish observed, inferred,
proposed, and executed work.

Then produce a Human Brief in plain language: what was learned, why it matters,
what changed, the recommended direction, meaningful trade-offs, remaining
uncertainty, and what artifact actually exists. Keep it concise but do not use
it as a substitute for the technical package.

Do not advance to implementation or OpenSpec unless explicitly requested.
Requester dissatisfaction, a correction, or a depth objection reopens the
Living Brief and triggers another evidence-bearing batch.

Load `references/hermes-delivery.md` for detailed package gates and report
evaluation.

## Hermes runtime adapter

- Use Hermes-native tools only when exposed. Do not assume LangGraph,
  LangChain, `ask_user_question`, or another host's state model exists.
- Never call a named tool merely because another host exposes it; use ordinary
  dialogue when Hermes lacks the equivalent capability.
- Use `session_search` for relevant earlier dialogue and `memory` only for
  durable cross-run preferences, never current task state.
- Treat interrupted work as `unknown`; inspect artifacts and live delegation
  logs before retrying with a new attempt ID.
- Keep installed Skill files read-only during research. Store all run state and
  deliverables in the writable task workspace.
- Use `research-tree-debug` only when available and explicitly diagnosing
  behavior; trace failure must never block research.
- Use `scripts/hermes_skill_adapter.py` only for package validation, prompt-risk
  diagnosis, gateway-log diagnosis, hook rendering, or staging.

## Completion standard

Finish only when the Alignment Checkpoint and autonomy handoff are supported,
the active plan-to-execute DAG has no unresolved required item, decisive
claims have traceable evidence, contradictions are resolved or explicitly
bounded, the Insight Digest has influenced decisions, both deliverables pass
their gates, and artifact claims match what was actually executed.
