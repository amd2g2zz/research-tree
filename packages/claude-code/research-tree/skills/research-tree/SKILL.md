---
name: research-tree
description: "Use when technical research needs evidence and alignment: turn vague or evolving questions, source material, and repositories into a recursively aligned Technical Research Package and Human Brief; test feasibility, research autonomously, and create OpenSpec only when requested."
argument-hint: "[research request, links, or repository]"
disable-model-invocation: false
user-invocable: true
---

# research-tree

## Purpose

Use `research-tree` when the requester is still discovering the problem as well
as when the requested research is already precise. Treat research as a joint
epistemic process:

- the requester is authoritative about preferences, desired outcomes, and
  permissions, but not about technical feasibility; a stated budget, deadline,
  or quality target can make the requested combination impossible;
- the agent contributes reconnaissance, counterevidence, and structure, but its
  interpretation is also provisional and may be wrong;
- user feedback, agent self-correction, and external evidence all update one
  evolving **Living Brief**;
- the research tree is a replaceable execution view of current understanding,
  not the final product and not proof that alignment is complete.

Produce two final outputs:

1. a cited **Technical Research Package** that can drive implementation; and
2. a professional **Human Research Report** (persisted as the Human Brief
   artifact) explaining the current direction, important choices, evidence,
   uncertainty, and what actually exists. It must be deep enough to support a
   human decision, not a shallow summary.

Create OpenSpec artifacts only when explicitly requested.

## Activation contract

Use this ordered state machine on Codex, Claude, and Hermes:

`verified_load -> bounded_reconnaissance -> alignment_question -> explicit_handoff -> autonomous_dispatch`

Positive trigger: a request for deep technical research, evidence, and a
decision-ready deliverable. Negative triggers: ordinary explanation, a small
edit, a one-shot factual answer, or an unrelated request. Negative triggers
must not start reconnaissance or dispatch.

Before `explicit_handoff`, do not dispatch, delegate, call external research,
or write a final research artifact. If the loader receipt is missing or stale,
alignment is not at equilibrium, a resource is unavailable, or handoff is not
explicit, return a bounded blocked disposition with the failed phase and next
safe action.

## Load the bundled resources

- Resolve every relative path against the skill directory supplied by the host.
- Read `references/research-quality-playbook.md` before beginning alignment or
  research.
- Read `references/alignment-controller.md` and initialize its run state before
  the first alignment question. Run its `plan` command immediately before
  every pre-handoff question and `record` immediately after the response.
- Use `assets/brief-template.md`, `assets/research-strategy-template.md`,
  `assets/technical-research-package-template.md`, and
  `assets/human-brief-template.md` for their corresponding artifacts.
- Read `references/blueprint-generation-research.md` only when forming or
  revising the Blueprint Target and Decision Map.
- Read `references/product-contracts.md` only when exact persisted schemas or
  runtime artifacts matter.
- Read `references/research-tree-architecture.md` before initializing,
  expanding, pruning, or closing a recursive research tree.
- Read `references/debug-tracing.md` only for explicit behavior diagnosis or debug mode.

## Claude Code runtime adapter

This is the Claude Code package of `research-tree`. Invoke with `/research-tree`
and use only capabilities exposed by the current session; never call tools from
another host merely because they appear in examples.

### Activation probe
`research-tree-activation-contract:v1:claude`
Follow `references/skill-activation.md`: only exact `/research-tree activation-probe v1 <correlation-id>` or its plugin-qualified form may return only `research-tree-activation:v1:claude:<correlation-id>` without tools; paths and links are `activation_unverified`.

- Resolve bundled resources from the active skill directory, including
  `${CLAUDE_SKILL_DIR}` when the host provides it. Do not resolve
  `references/` or `assets/` from the user's working directory.
- Read `references/claude-code-compatibility.md` before the first alignment or
  research action, as well as before Claude-specific installation or hooks.
  Before handoff, delegation, compaction, or recovery, also read
  `references/claude-native-orchestration.md`.
- When the current session exposes `AskUserQuestion`, use it only for a rare
  discrete decision after open-ended intent guidance and before the Research
  Strategy handoff. After the
  handoff, do not use it for ordinary research decisions; revise the strategy
  autonomously within the granted authority. Otherwise use ordinary dialogue
  during pre-handoff alignment; never assume `AskUserQuestion`,
  `ask_user_question`, or another host tool exists.
- In Claude Code, "I don't know", "I don't understand", or a correction means
  the brief needs teaching or verification. Explain the missing context in
  plain language, update the Living Brief, and continue the bounded research
  cycle; never treat it as a stop signal.
- When the requester gives a concrete failure mode, inspect the relevant source,
  consult available documentation or web search, and try safe alternatives
  before asking another generic preference question. Do not finish after only
  listing causes, options, or proposed fixes; return an evidence-bearing interim
  result in the same turn. Ask only for a consequential choice that cannot be
  recovered autonomously.
- Treat the installed package as read-only; keep research reports, briefs,
  evidence ledgers, and other task artifacts in the writable workspace.
- After strategy handoff, map ready waves onto Claude Code's native task list
  and Agent tool when exposed. Launch independent agents together, use
  background execution only when the host supports it, and continue coordinator
  work instead of polling. Use an agent team only when workers must debate or
  exchange discoveries; independent research remains cheaper and clearer as
  isolated leaf agents.
- Treat subagent messages as self-reports. Read the requested Finding Pack,
  inspect decisive evidence, and reconcile contradictions before updating the
  shared ledger. Keep auto-memory and conversation resume as secondary context;
  the workspace checkpoint is authoritative after compaction or restart.
- Dispatch an Agent only after `start`, then bind the exact returned child
  identity with `bind-agent`. Claude Finding Pack submission fails without the
  active attempt binding, and one child identity cannot bind two attempts. The
  `PostToolUse:Agent` and `SubagentStop` hooks retain only sanitized opaque
  identity fields; unmatched identity remains `unknown_outcome`.
- After handoff, use `scripts/native_execution_adapter.py` with host argument
  `claude` for atomic task attempts, crash recovery, Finding Pack validation,
  and completion checks when Python is available. The native task list mirrors
  this state; it does not replace it.
- When the checkout runtime is available, use the stable lifecycle sequence
  `research-tree install`, `research-tree doctor`, `research-tree run`,
  `research-tree resume`, `research-tree status`, and `research-tree verify`.
  Supply ordinary workspace and plain-language authority inputs, never
  HostEvent or SQLite inputs. `prepared` and
  `verification_pending` remain non-authoritative receipts with no completion
  authority.
- Before selecting dynamic phases, run `probe-host` with explicit session
  capability observations. Build bounded phase/child projections with
  `project-workflow`, explicitly selecting Agent, Workflow, or hybrid mode. A
  failed or denied native surface selects `coordinator-dispatch-v1`; never infer
  availability from a task-list UI or reuse a stale capability digest. Live
  Workflow and hybrid claims additionally require native run/task/script
  identity, a script digest, phase IDs, and hybrid child IDs.
- The installed package contains `SKILL.md`, bundled references/assets, and the
  dependency-free native execution adapter. It does not contain the repository
  Python runtime, lifecycle hooks, builder, or evaluation corpus.

### Source checkout development boundary

When Claude Code is operating inside the `research-tree` source checkout and
the requester explicitly asks for development, packaging, hooks, or evaluation
work, these repository paths are available:

| Path | Role | Development contract |
| --- | --- | --- |
| `hooks/research_hook.py` | Lifecycle hook launcher | Run through `uv run` from the checkout; it imports `research_tree` and is not part of the installed skill package. |
| `src/research_tree/` | Python artifact runtime | Edit only when the task changes runtime behavior; use the public API and run the full test suite. |
| `scripts/` | Host package builder and Hermes staging/validation tools | Run `python scripts/build_skill_packages.py --check` after package-affecting changes. |
| `evaluation/` | Evaluation cases and forward-test material | Treat as development/evaluation input, not as a user research source or runtime dependency. |

Before using these paths, verify the checkout with `pyproject.toml`, `src/`,
`skill-src/`, and `packages/`. Run `uv sync` first. Do not claim that an
installed `/research-tree` package can execute these files; when the checkout
is unavailable, report the missing development capability and continue with
the host-native skill workflow.

### Claude Code hooks

Hooks are opt-in repository settings, not normal Skill behavior. Read the
compatibility reference before explicitly enabling them; never enable them for
an ordinary research run.

## Product Rules

- Unless the requester explicitly says not to discuss and to execute directly,
  treat the initial research request as exploratory and materially incomplete,
  even when it sounds syntactically specific.
- Do not answer an exploratory request with only a questionnaire, option table,
  plan, or research tree. First run bounded reconnaissance and give the
  requester knowledge they did not yet have.
- Optimize for solving the requester's problem, not for displaying the
  research protocol. Keep Living Briefs, claim ledgers, Decision Maps, and
  tree revisions as internal working state unless exposing a small part of
  them helps the requester understand or decide. Use progressive disclosure;
  never make the requester operate the schema.
- Treat a vague, short, incomplete, or contradictory brief as a difficulty
  signal, not permission to invent missing requirements. Search or inspect the
  smallest useful evidence set, teach the missing distinction, and guide the
  next decision in a later short turn.
- Inspect the current repository, supplied artifacts, and relevant context
  before asking detailed questions. If the request contains independent problem
  areas, expose a workable decomposition before refining their details.
- Keep every user-facing interactive turn under 1000 characters. Split work
  across short purposeful rounds using: progress, new information, impact, one
  decision/reflection, and next step. Internal reports and persisted artifacts
  may be longer; do not paste them into the conversation by default.
- Persist an alignment-turn record after each meaningful pre-handoff exchange:
  current mirror, one intent/knowledge gap, evidence added, response summary,
  human and agent belief delta, and decision effect. If no field changes, do
  not repeat the question; run a new bounded reconnaissance step instead.
- Rewrite the apparent intent and reasonably expand its scope when
  reconnaissance exposes missing outcome, evaluation, authority, lifecycle,
  safety, integration, or operational dimensions. Label every expansion as an
  agent proposal rather than a user requirement.
- Use one open-ended, guided prompt at a time to help the requester express
  their own intent. Do not use multiple-choice menus as the default discovery
  mechanism. Explain alternatives as examples or contrasts; reserve structured
  question tools for a rare discrete decision after the distinction is
  understood.
- In each alignment turn, briefly mirror the current understanding, identify
  one consequential gap, add the smallest useful evidence or example, and
  invite the requester to elaborate, correct, or challenge it in their own
  words. On the next turn, reconstruct the intent and state what changed.
- No pre-handoff turn may be question-only. It must add the minimum useful
  knowledge, teaching, counterevidence, or concrete example before guiding the
  requester toward a reflection or decision.
- When the requester signals confusion, missing vocabulary, or uncertainty,
  pause preference questions and run a teaching reconnaissance cycle: inspect
  the smallest useful set of web, repository, or supplied sources; explain the
  result in plain language; show one implication, example, or trade-off; then
  ask one open-ended guided reflection question. Do not answer "I don't know"
  before trying the available evidence paths.
- When the host exposes a structured input tool, use it only for a genuinely
  discrete bounded decision after open-ended elicitation. Put the
  reconnaissance-derived knowledge and consequences in the surrounding
  response; the tool is a transport for that choice, not a substitute for
  mutual understanding. Never call a named tool merely because another host
  provides it.
- Repeat reconnaissance and dialogue as needed. Do not assume that one exchange
  can align a vague problem.
- Treat "I don't know", "I don't understand", "not sure", and corrections as
  work signals, not refusal, blockage, or permission to end. Translate the
  feedback into missing knowledge, update the Living Brief, and run the next
  bounded inspection, search, or experiment.
- When feedback supplies a concrete pain point, do not repeat generic preference
  questions before making progress. Ask again only when a consequential,
  non-recoverable choice is genuinely required.
- Never end a requested investigation after only showing a research tree,
  option table, diagnosis, or proposed fix list. Deliver evidence-bearing
  progress in the same round: inspected sources, repository facts, a safe
  experiment, or a scoped feasibility result. "Recommendations only" means do
  not edit the target system; it does not mean skip the research or report.
- A Blind-Spot Packet, interim note, or Human Brief is not the final research
  report. If the requester asks for a report while the Living Brief is still
  `exploring` or `reopened`, label the response as interim, state what evidence
  and intent decisions are missing, and continue bounded research. Do not
  compress unfinished research into a final-looking brief.
- A worker may report a blocker only after searching available sources and tools,
  inspecting local references or the repository, and trying safe alternatives.
  Record the missing capability and evidence. "I don't know" by itself is not
  a blocker.
- Treat every user technical assertion and every agent technical assertion as a
  claim with provenance and evidence status. Do not silently obey, overrule, or
  promote either side's assertion to fact.
- Before any implementation, target edit, or irreversible experiment, emit an
  **Alignment Checkpoint** stating the goal and deliverable, scope and
  non-goals, authority and environment, success oracle, unresolved high-impact
  decisions, and feasibility. Do not act while a high-impact field is unknown
  or agent-selected: continue reconnaissance and guide one open-ended intent
  dimension at a time. Silence,
  "okay", or "continue" is not alignment evidence. Explicit execute-direct
  permits a provisional checkpoint but does not waive safety, authority, or
  feasibility checks.
- Test whether outcome, scope, quality, explicitly stated budget, time,
  environment, authority, and required evidence are mutually consistent before building an
  implementation-oriented research tree. Human insistence does not make an
  infeasible combination feasible.
- Do not invent a monetary budget or use API/token spend as a default reason to
  narrow, stop, or reject long-horizon research. Treat this class of work as
  cost-tolerant unless the requester explicitly supplies a financial cap.
  Distinguish that policy from operational guardrails such as time slices,
  tool-call batches, concurrency, storage, safety, and host limits. When an
  operational guardrail is reached, persist the checkpoint and continue in a
  later batch or resume cycle; do not report the research as infeasible merely
  because a guardrail ended the current batch.
- Classify each stated constraint as `hard`, `preference`, `aspiration`, or
  `estimate` from its wording and dialogue anchors. Do not silently relax a hard
  constraint or reject the task because a negotiable aspiration is unmet.
- State infeasibility plainly when proportionate evidence establishes it. Give
  the conflicting constraints, relevant bound or baseline, confidence, and the
  nearest feasible reframings. Do not hide a negative feasibility result behind
  an elaborate tree or aspirational architecture.
- Do not silently replace an infeasible request with the agent's preferred
  feasible substitute. Present reframings and their trade-offs, but wait for
  the requester to select or explicitly delegate a changed outcome before
  expanding one into an implementation plan.
- Do not declare a request impossible from intuition alone. When the quick
  evidence cannot decide, label it indeterminate and run only the smallest
  feasibility spike that could change the disposition.
- Treat user feedback as part of the Living Brief. When feedback reveals an
  agent error, record the correction and revise the intent, scope, or tree;
  never reduce it to a cosmetic report edit.
- Do not ask for facts that can be learned from supplied material, repository
  inspection, proportionate external research, or a safe experiment.
- Never choose a familiar technical vertical, target, user, tool, or
  architecture without evidence from the current Context Pack and
  reconnaissance.
- Maintain exactly one active research tree. A changed tree supersedes its
  predecessor and records why; do not present several trees as “latest.”
- During deep research, continuously test the early understanding. After the
  Research Strategy handoff, revise the Intent Model, Working Brief, strategy,
  and active tree autonomously when evidence changes the desired outcome,
  scope, authority, success definition, risk boundary, or a premise. Do not
  re-enter ordinary collaboration after handoff; stop only when the existing
  authority or safety boundary cannot support a responsible continuation.
- Produce concrete design decisions, implementation consequences, and honest
  artifact evidence. A compiled report is not an executed system.
- Produce both co-primary deliverables: a deep, evidence-bearing Technical
  Research Package for implementation and a faithful, plain-language Human
  Brief for the requester. Never substitute the brief for the package, or the
  package for human understanding.
- Do not advance to implementation, OpenSpec conversion, or a dependent round
  until both deliverables pass their gates. The package must be actionable and
  the requester must be satisfied with the Human Brief. Dissatisfaction,
  correction, or a depth objection reopens the Living Brief and requires a new
  evidence-bearing batch. Silence or "okay" is not acceptance.

## Inputs and authority

Accept any combination of requests, links, notes, screenshots, repositories,
prior outputs, feedback, and constraints as the **Context Pack**. Preserve the
requester's grouping as Context Bundles while ledgering individual inputs.

For each input record kind, origin, readable scope, revision or content
identity, role, and authority boundary. Repository inputs include path or
remote, revision when available, readable scope, and reconnaissance baseline.
Do not silently reuse changed inputs or old findings as current facts.

Distinguish these evidence classes throughout:

- explicit user preference, objective, or authorization;
- user technical assertion or hypothesis;
- agent interpretation or hypothesis;
- repository observation;
- external source claim; and
- experiment result.

The first class controls intent and permission, but cannot override physical,
technical, economic, or logical bounds. Treat user-supplied budgets, deadlines,
and quality bars as constraints to test for consistency, not evidence that the
desired result exists. The other classes remain falsifiable. When inputs
conflict, preserve their distinct anchors, scope, and uncertainty.

## Use available capabilities

At activation, map available host capabilities by function rather than product
name: structured user input, web retrieval, repository/file inspection, shell
or sandbox execution, persistent artifacts, and delegated workers. Use only
capabilities actually exposed in the current session.

- Use ordinary dialogue for alignment by default, even when a structured
  question tool exists; use the structured tool only for a rare discrete
  decision after open-ended intent elicitation.
- Use the host's available search and browsing tools; do not require one named
  provider.
- Run experiments only when a safe execution surface is available. Otherwise
  record the missing evidence without upgrading its level.
- When debug tracing is enabled and `research-tree-debug` is available, emit sanitized phase events from `references/debug-tracing.md`; trace failure must never block research or target work.
- Delegate only when a worker/subagent mechanism is available; otherwise run
  independent tracks sequentially.
- Preserve the fields in bundled table templates, but render them as labeled
  bullets when the current messaging channel does not support Markdown tables.
- Store long-lived research state in a writable workspace location. Treat the
  installed skill directory as read-only unless the user explicitly requests a
  skill update.

### Autonomy envelope after strategy handoff

Once the Research Strategy is selected, declare the control handoff and
autonomy envelope before starting long-horizon work:

- autonomous choices: all research, tool, delegation, scheduling, intent
  revision, and strategy revision decisions within the granted authority;
- hard stop triggers: the current authority or safety boundary is insufficient,
  a required capability is unavailable, or the completion oracle cannot be
  evaluated honestly;
- continuation state: the Living Brief revision, active tree revision,
  Decision Map, work status, evidence ledger, and next batch;
- completion oracle: the evidence standard and delivery conditions; and
- failure policy: retry or replan recoverable failures, persist a blocker with
  evidence for unrecoverable failures, and never silently downgrade the goal.

After each meaningful batch, persist the continuation state before returning a
response. If evidence invalidates the current strategy, create a successor
revision internally and continue; do not wait for another user approval. A hard
stop records the missing capability or boundary and a fallback, without
silently expanding authority.

## Collaborative alignment loop

### Internal dialogue state gate

Before composing any user-facing question, update the SQLite-backed temporal
Alignment Graph with separate human beliefs, agent beliefs, evidence,
disagreements, and strategy hypotheses. Run the `plan` command from
`scripts/alignment_controller.py`. It may return
only `ask_one`, `reconnaissance`, or `await_human_confirmation`; never bypass
it by asking a compound question. The controller selects at most one human-only,
high-impact node. After the response, run `record` with the observed outcome.
Two unchanged fingerprints trigger reconnaissance instead of another question;
six alignment turns or two asks for one node trigger evidence-based resolution
or a visible draft with explicit assumptions, never automatic handoff. Do not
show the internal graph to the requester as a questionnaire.

### 0. Co-evolve cognition before strategy handoff

The Research Strategy must emerge from a mutual cognition loop, not from an
agent proposal followed by a yes/no approval. Before handoff, repeat this
sequence as long as new evidence can change the direction:

1. expose the agent's current reading, evidence, assumptions, blind spots,
   strongest counterargument, and consequence if wrong;
2. invite the requester to add context, constraints, priorities, corrections,
   or counterclaims in their own words; do not force a menu selection;
3. test the new input, provide counterevidence or alternatives, and state what
   changed in the human and agent models;
4. update the Intent Model, Living Brief, claim ledger, and open disagreements;
5. check whether the next research decision is now better determined.

Persist the turn record before returning control. The record is structured
state, not a transcript: never store prompts, full responses, secrets, or
unbounded free-form notes in debug traces.

Inspect existing project context before detailed elicitation. Work on one
consequential knowledge or intent gap per user-facing turn. If the request
contains independent problem areas, make the decomposition visible first.
Present the evolving understanding in small sections and ask for correction,
extension, or counterargument, not approval. Candidate interpretations are
hypotheses that help the requester think; they are not a menu the requester
must select from.

The strategy handoff has two gates. First, the agent may prepare a decision
equilibrium draft, not declare alignment complete. Second, it must show the
strategy projection derived from the Alignment Graph and receive explicit confirmation
of the outcome, scope, authority, and autonomous-research transition. The
equilibrium requires visible belief evolution, a supported feasibility
disposition, an actionable success oracle, and no unresolved
high-impact choice whose outcome still depends on the requester. Before that
point, humans and agent are collaborators; after it, the agent owns execution,
replanning, delegation, and intent correction within the granted authority.
Native question tools are only transports for rare discrete choices in this
pre-handoff loop, not substitutes for open-ended intent elicitation, debate, or
a reason to stop early.

### 1. Inventory and run rapid reconnaissance

Inspect all supplied material before proposing a direction. For repositories,
identify relevant behavior, entry points, modules, interfaces, data/state flow,
dependencies, tests, deployment path, and likely change surface. Use bounded
external search when needed for current terminology, adjacent approaches,
feasibility, counterexamples, known bounds, baseline costs, and prerequisite
resources. Perform an order-of-magnitude sanity check when requested scope,
quality, budget, or schedule could conflict.

Reconnaissance is not the final research. Its purpose is to improve the next
human-agent conversation.

### 2. Return a Blind-Spot Packet

For an exploratory request, return a compact packet containing:

- **Current reading:** what outcome the request appears to seek and which parts
  are explicit versus inferred;
- **Blind spots:** missing distinctions, hidden decisions, mistaken premises,
  adjacent problem classes, and consequences the wording does not expose;
- **Knowledge gained:** a small amount of inspected evidence that changes what
  choices are available; include counterevidence where relevant;
- **Feasibility disposition:** `plausible`, `conditional`, `infeasible`, or
  `indeterminate`, with the decisive constraint relationships and confidence;
- **Intent rewrite:** a stronger statement of the likely task;
- **Reasonable scope expansion:** dimensions that should be included and why,
  with explicit guardrails against unwanted expansion;
- **Open disagreements and unknowns:** including possible agent error; and
- **Next decisions:** one guided prompt or rare discrete decision whose answer
  now has a visible consequence.

Do not force false alternatives. When evidence cannot rank domains, recommend
a discovery method or evaluation criterion instead of selecting one.

### 3. Update the Living Brief

Keep one versioned Living Brief across dialogue and research. It is accumulated
joint state, not an approval receipt or a rewritten copy of the user's message.
Intent understanding remains active throughout the round: repository facts,
external findings, experiments, and worker results may change the current
interpretation even after a strategy has been selected. After each meaningful
batch, explicitly test whether the desired outcome, scope, authority, success
oracle, or a premise affecting a human choice has changed. Revise the Intent
Model and Working Brief before continuing when it has.
Record:

- original and later user requests;
- explicit preferences and authorization boundaries;
- the agent's current intent rewrite and proposed scope expansion;
- the claim ledger with claimant, status, confidence, evidence, consequence if
  wrong, and validation path;
- Blind-Spot Packets and knowledge introduced to the conversation;
- user feedback and corrections;
- agent self-corrections;
- unresolved disagreements and unknowns;
- the current feasibility disposition and constraint-consistency record;
- the current provisional working frame; and
- revision history and supersession reasons.

Use claim statuses `asserted`, `hypothesis`, `supported`, `refuted`, `unknown`,
or `superseded`. Use brief states `exploring`, `provisionally-aligned`,
`reopened`, or `superseded`.

### 4. Decide alignment and feasibility disposition

Alignment is provisional, never a declaration that both sides are factually
correct. Separately assign one feasibility disposition:

- `plausible`: no material contradiction is currently supported;
- `conditional`: the outcome depends on explicit assumptions or relaxed
  constraints;
- `infeasible`: evidence shows the current outcome and hard constraints cannot
  be satisfied together; or
- `indeterminate`: available evidence cannot yet distinguish the above.

Start implementation-oriented deep research only when:

- the current outcome, deliverables, and authority boundary are mutually
  understandable;
- the intent rewrite and scope expansion are visible to the requester;
- material knowledge disagreements are resolved or have an explicit validation
  path;
- success and evidence criteria are actionable; and
- remaining uncertainty no longer blocks selection of the next research
  questions; and
- feasibility is `plausible` or `conditional`, with every condition visible.

If these conditions are not met before strategy handoff, use the next response
to add knowledge and continue the collaborative loop. A feedback or correction turn must produce an evidence-bearing
interim artifact before returning control, unless the requester explicitly says
to pause or stop. Do not repeatedly ask the same question without new evidence.
Use a structured question tool when available only during this pre-handoff
collaboration for a rare bounded discrete decision after open-ended guidance,
and continue from its answers as new Living Brief evidence. If the requester
explicitly says to skip discussion and execute, record a provisional internal
frame, assumptions, and boundaries, then apply the same feasibility rule
without waiting for dialogue; explicit execution does not grant unsafe or
unspecified permissions or make contradictions feasible.

For `infeasible` before handoff, stop before creating an implementation research
tree. Deliver the feasibility finding and ask which outcome or constraint, if
any, may be changed; use a structured question tool when available. Do not
elaborate a replacement plan before that choice. After handoff, the agent
selects an internally feasible replan within its authority or records a hard
stop with fallback. For `indeterminate`, create only a bounded
feasibility investigation with a decisive oracle. A full research tree is
warranted only after that
investigation changes the disposition, unless the requested deliverable is
itself a rigorous feasibility or impossibility study.

## Build the active research strategy

Create a strategy from the current Living Brief only after the feasibility rule
above permits it. Include:

- the technical outcome and implementation decision to enable;
  - the alignment basis, handoff boundary, and internal supersession triggers;
- the Blueprint Target and Decision Map of design obligations;
- prioritized research tracks and decision-shaped subquestions;
- depth, source classes, operational guardrails, evidence standards, and exit criteria;
- repository baseline and expected change surfaces;
- experiment and representative-artifact contracts;
- the minimum viable technical loop and path to production; and
- final deliverables and whether OpenSpec conversion was requested.

Choose `bounded`, `standard`, or `deep` depth per track. Source counts are a
budget signal, not evidence of depth. Each Decision Slot records its intent
basis, impact, uncertainty, irreversibility, alternatives, anchors, closure
rule, validation oracle, fallback, and reversal condition.

Show the current Alignment Graph's strategy projection at handoff so the
requester can inspect the working direction. Display is not acceptance or
delivery. After explicit confirmation, compile open decision obligations and
anchored reconnaissance evidence into exactly one Research Tree revision zero.
Do not create or display a Research Tree before this boundary.

## Execute recursive deep research

Research autonomously while repeatedly testing both the user model and the
agent model. Intent understanding is not a completed preflight phase:

```text
Living Brief vN -> active tree vN -> retrieve / inspect / experiment
    -> atomic evidence -> intent and epistemic review
    -> update claims, brief, decisions, and active tree
    -> continue locally OR create an internal successor revision
```

After a user feedback or correction event, start a new bounded evidence batch
before ending the turn. Before handoff, return to collaboration only when a
material choice remains. After handoff, incorporate the feedback autonomously
and revise the successor state without requesting another approval.

After every meaningful search, repository-inspection, or experiment batch,
record:

- what evidence changed a user claim, an agent claim, or neither;
- what changed in the intent, scope, Decision Map, or research tree;
- whether the feasibility disposition or its supporting bounds changed;
- what remains weak, contradictory, or uncovered;
- whether more work can still change a decision; and
- whether to continue, supersede the tree, reopen dialogue, or stop.

Classify updates:

1. **Local refinement:** revise the one active tree autonomously and record the
   superseded revision.
2. **Material intent change after handoff:** produce an updated Intent Model,
   Working Brief, and successor strategy internally before continuing.
   Material choices are part of the autonomous handoff, not a new question to
   the requester.
3. **Evidence contradicts a user premise:** present the evidence, consequence,
   and viable choices; do not silently obey or overrule.
4. **Evidence contradicts an agent premise:** explicitly self-correct, update
   the Living Brief, and revise or supersede the tree.
5. **Feasibility changes:** internally replan when new evidence moves the
   disposition to `infeasible` or `indeterminate`; if no responsible path fits
   the granted authority, persist a hard stop and fallback. Do not preserve
   sunk-cost plans.

Use 2-4 decision-shaped subquestions per external track and varied search
formulations. Prefer primary research, official documentation, standards,
source code, release notes, first-party measurements, and repository evidence;
add independent evidence for transferability and criticism. Read decisive
sources in full. Snippets discover sources but do not anchor claims.

Record each atomic claim with source, version/date/context, applicability,
confidence, limitation, counterevidence, and affected Decision Slot. Mark
single-source claims unverified and preserve real contradictions. Every
externally verifiable consequential claim in the final deliveries needs an
inline link or exact source-ledger reference.

When testable, run a safe, bounded experiment with baseline, hypothesis,
metric/oracle, fixed operational guardrail, coherent change, regression guard, raw evidence,
and keep/discard result. Assign artifacts one evidence level: `proposed`,
`source-inspected`, `built`, `executed`, or `independently-reviewed`. When the
request asks for a usable or validated result, execute the smallest
representative artifact unless safety, permission, environment, or an explicitly
stated financial cap blocks it; record the blocker without inflating the
evidence level.

Stop a track when its decision-specific evidence standard is met, additional
work cannot change the decision within the agreed evidence scope, or the
remaining gap has an explicit fallback. Reaching a time/tool-call batch
guardrail creates a resumable checkpoint, not an automatic final stop. Do not
seek endless factual certainty. Reopen alignment only
when a material human choice is newly exposed, not for routine uncertainty.

When subagents are available, give each a disjoint decision question, source
boundary, budget, and Finding Pack schema. The coordinator owns contradiction
checks, deduplication, coverage, Living Brief updates, and synthesis. Workers
return atomic Finding Packs, not prose chapters.

Use the runtime's plan-to-execute loop when available, but do not precompile the
whole investigation as one static wave graph. Initialize revision zero from
the current Decision Map and all existing Finding Packs; historical evidence
forms the baseline and has zero realized delta. Dispatch only the current
dependency-ready frontier, ingest verified Finding Packs, compute the measured
ledger delta, grow structured successor actions, prune or defer dominated
branches, persist a new `research-tree-state` revision, and select the next
frontier. Selection targets bounded residual Decision Slot risk, upweights
failed validation, and normalizes value by observed branch complexity; worker
confidence is never an update signal. Continue until Decision Slot closure
oracles pass. An empty static task list is not a stop condition.

Workers may propose growth only through structured `research_continuations`
with a triggering evidence reference, missing evidence, and closure oracle.
The coordinator owns expansion, deduplication, value scoring, penalties, and
stop decisions. Do not hand a broad track to one worker or let workers re-delegate.
Available worker capacity left unused without a dependency,
safety, duplicate, or capability reason is a conformance failure.

The coordinator must synthesize across workers before drafting delivery. Treat
Insight Digest signals `uncovered`, `thin`, `contested`, and `qualified` as
successor-work triggers, not report-writing cues. Only a `converging` slot may
advance to Decision Ledger review, and final delivery remains blocked while an
active P0 slot lacks completed depth, counterevidence, or validation evidence.
Even after all slots close, keep the persisted tree in `delivery_pending` until
both the Technical Research Package and Human Research Report are present and
verified through the canonical delivery authority; a closed tree without the two reports is not a
completed research round.

## Produce the deliveries

### Technical Research Package

Include, where applicable:

1. round, Context Pack, current Living Brief state, and alignment evolution;
2. current intent rewrite, scope expansion, authority, and unresolved issues;
3. feasibility disposition, constraint conflicts, bounds, assumptions, and
   nearest feasible reframings;
4. epistemic change log showing user and agent claims changed by evidence;
5. repository baseline and exact paths or symbols;
6. Blueprint Target, Decision Map, alternatives, and closure status;
7. strategy, atomic findings, evidence coverage, contradictions, and limits;
8. recommended architecture, interfaces, state/failure semantics, agent/tool
   loop, permissions, safety, deployment, and operations as relevant;
9. ordered implementation work with dependencies, validation, and rollback;
10. experiments and artifact evidence with commands, results, raw paths, and
   honest evidence levels;
11. risks, fallbacks, reversal conditions, Source Ledger, and traceability.

### Human Research Report (Human Brief artifact)

Explain in decision-oriented language:

- what the joint understanding became and how it changed;
- whether the requested combination is plausible, conditional, infeasible, or
  still indeterminate, and why;
- where the requester corrected the agent and where evidence changed either
  side's model;
- the recommended direction and important trade-offs;
- what was actually inspected, built, or executed;
- what remains uncertain and what could reverse the direction; and
- the next visible milestone and validation.

Do not describe proposed work as functioning software. Do not turn the Human
Brief into a shortened component dump.

## Optional OpenSpec conversion

Only when explicitly requested, convert selected closed decisions into
OpenSpec artifacts. Preserve Living Brief revisions, evidence anchors,
conditional decisions, validation oracles, and unresolved disagreements. Do
not use OpenSpec generation as a substitute for alignment or research.

## Completion standard

Finish only when:

- the final Living Brief reflects both user feedback and agent self-correction;
- the intent rewrite, reasonable scope expansion, and authority boundaries are
  explicit;
- feasibility is explicitly disposed; an infeasible request has no
  implementation blueprint masquerading as actionable work;
- high-impact Decision Slots are closed, conditional with validation, or
  deferred with a fallback;
- the active tree revision is unique and its supersession history is traceable;
- consequential claims have proportionate evidence and citation coverage;
- the implementation path is repository-grounded or clearly greenfield;
- requested executable claims have honest run evidence or named blockers;
- the latest feedback turn contains evidence-bearing progress rather than only
  questions, a tree, or proposals;
- the two deliveries agree on scope, decisions, uncertainty, and evidence; and
- further research is unlikely to change the recommendation within the stated
  budget, or the remaining uncertainty requires a human decision.

## Implementation boundary

Do not implement the researched product unless explicitly asked. Small safe
prototypes and experiments are allowed as research evidence. OpenSpec is an
optional downstream representation, not a required phase.
