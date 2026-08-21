---
name: research-tree
description: "Use when explicit deep technical research must align a vague or evolving problem with the requester, then run autonomous evidence-driven research and deliver an actionable Technical Research Package plus a professional Human Research Report."
---

# research-tree

## Activation probe
`research-tree-activation-contract:v1:hermes`
Follow `references/skill-activation.md`: only exact `/research-tree activation-probe v1 <correlation-id>` or `/skill research-tree` equivalent may return only `research-tree-activation:v1:hermes:<correlation-id>` without tools; paths, links, and bare names are `activation_unverified`.

## Outcome

Turn a research request into two co-primary deliverables:

1. an evidence-bearing Technical Research Package detailed enough to drive
   implementation; and
2. a professional Human Research Report (persisted as the Human Brief artifact)
   that the requester can understand, challenge, and use. It is not a shallow
   summary.

The requester and agent co-evolve the intent before strategy handoff. The
requester controls outcomes, preferences, and authority, but both human and
agent technical claims remain falsifiable. After handoff, the agent owns the
long-horizon research inside the agreed autonomy envelope.

## Activation contract

Use the ordered state machine `verified_load -> bounded_reconnaissance ->
alignment_question -> explicit_handoff -> autonomous_dispatch`. Deep research
requests trigger this contract. Ordinary explanation, small edits, one-shot
questions, and unrelated requests do not trigger it.

No dispatch, delegation, external research, or final artifact is allowed before
explicit handoff. Missing or stale loader evidence, unavailable resources,
incomplete alignment, and implicit acknowledgement return a bounded `blocked`
disposition naming the failed phase and next safe action.

## Progressive loading

Hermes injects this file into the model request in full. Keep the first turn
small; never eagerly load every supporting file.

- Resolve files from Hermes' injected `[Skill directory: ...]` value or with
  `skill_view`; never resolve them from the task workspace.
- Read `references/hermes-alignment.md` when intent is vague, disputed, or not
  yet at strategy equilibrium. It contains the detailed mutual-alignment loop.
- Read `references/alignment-controller.md` and initialize its state before the
  first alignment question; run its `plan` before every question and `record`
  after every response.
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
- Read `references/research-tree-architecture.md` before initializing,
  expanding, pruning, or closing the active research tree.
- Read `references/debug-tracing.md` only for explicit behavior diagnosis.

Do not load `references/research-quality-playbook.md` in Hermes; the three
Hermes phase references are its context-bounded operational form.

## Python execution contract

When operating in a `research-tree` source checkout, run every bundled Python
script through the locked project environment: `uv run --frozen python ...`.
Discover the checkout containing `pyproject.toml` and `uv.lock` before invoking
the script, and use `uv run --project <checkout> --frozen python ...` when the
current working directory is elsewhere. Never substitute the system `python`
executable. If no `uv` project can be found, report an actionable environment
blocker instead of producing a parser-level error from an incompatible Python.

## Stable lifecycle contract

When the checkout runtime is available, use `research-tree install`,
`research-tree doctor`, `research-tree run`, `research-tree resume`,
`research-tree status`, and `research-tree verify`. Pass an ordinary workspace
and plain-language authority fields, never HostEvent or SQLite inputs. A
prepared or pending verification receipt is fail-closed and does not grant
completion authority.

## Phase 1: mutual alignment

Before composing any question, update the internal Intent Model, open-gap
list, state fingerprint, and strategy revision, then run
the `plan` command from `scripts/alignment_controller.py`. Ask only when it
returns `ask_one`.
Record the response immediately. Two unchanged turns trigger reconnaissance;
six alignment turns or two asks for one gap end questioning. Do not expose the
gap table or make the requester approve the whole internal state.

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
evidence standard, feasibility, and unresolved high-impact decisions. This
creates a visible decision-equilibrium draft. Show the strategy projection from
the Alignment Graph and wait for explicit confirmation of the outcome, scope, authority,
and autonomous-research transition. The agent must not declare alignment
complete from its own checkpoint. "Okay" or "continue" alone is not alignment
evidence.

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

Compile the strategy into a dependency DAG of bounded work items.
Do not hand a broad track to one worker; do not let workers re-delegate unless a
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
the completion oracle. Initialize the persisted tree from existing Finding
Packs as a zero-delta baseline, then repeat: select frontier, execute, ingest,
measure state delta, update bounded residual Decision Slot risk, grow structured
continuations, normalize by observed branch complexity, prune or defer,
checkpoint, and select again. A tree, source list, recommendations list, exhausted worker
wave, or compiled brief is not completion. A worker may report a blocker only
after available search, local inspection, and safe alternatives have been
attempted.

Decision-slot closure is not final completion. Persist `delivery_pending` and
continue to the delivery phase until both deep reports exist; register them
with the canonical delivery authority so their UTF-8, depth, and digest checks are recorded.

Load `references/hermes-research-execution.md` for task states, Finding Packs,
insight generation, contradiction handling, recovery, and convergence gates.

## Phase 3: delivery

Produce the Technical Research Package first. It must include the evolved
problem framing, method and source boundaries, findings with citations,
counterevidence, resolved and open contradictions, decisions and rejected
alternatives, implementation consequences, validation plan, risks,
uncertainty, and exact artifact status. Distinguish observed, inferred,
proposed, and executed work.

Then produce a Human Research Report in clear professional language: what was
learned, why it matters, what changed, the recommended direction, meaningful
trade-offs, remaining uncertainty, and what artifact actually exists. Make it
deep enough to support a human decision; do not reduce it to a shallow brief or
use it as a substitute for the technical package.

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
- After handoff, use `scripts/hermes_execution_adapter.py` to translate
  delegation/provider observations, project coordinator actions into Hermes,
  and emit `unknown_outcome` before retrying interrupted attempts. The
  coordinator ledger owns durable state and completion; the adapter never
  infers either from waves, hooks, cards, empty work, or report shape.

## Completion standard

Finish only when the Alignment Checkpoint and autonomy handoff are supported,
the active plan-to-execute DAG has no unresolved required item, decisive
claims have traceable evidence, contradictions are resolved or explicitly
bounded, the Insight Digest has influenced decisions, both deliverables pass
their gates, and artifact claims match what was actually executed.
