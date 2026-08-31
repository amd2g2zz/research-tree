---
name: research-tree
description: "Use when technical research needs evidence and alignment: turn vague or evolving questions, source material, and repositories into a recursively aligned Technical Research Package and Human Brief; test feasibility, research autonomously, and create OpenSpec only when requested."
---

# research-tree

## Purpose

Run technical research as a joint epistemic process. The requester is
authoritative about preferences, outcomes, and authority, but not about
technical feasibility. The agent contributes reconnaissance, counterevidence,
and structure, and is equally provisional. User feedback, agent
self-correction, and external evidence update one Living Brief. Produce two
co-primary deliverables: a cited, evidence-bearing Technical Research Package
able to drive implementation, and a professional Human Research Report (the
Human Brief artifact) deep enough to support a human decision. Create OpenSpec
artifacts only when explicitly requested.

## Goal model

- The confirmed StrategyProjection is the primary goal. Its decision_targets
  and success_oracles define what the run may claim and when it may complete.
- Decision Slots are secondary: each slot carries a required `serves` link
  (target_id plus oracle_ids) into a confirmed target and oracle. No
  confirmed projection means no dispatch.
- Truth is artifact-decided: Finding Packs, goal-contribution assessments,
  and per-oracle satisfaction registrations decide outcomes. Worker
  confidence, agent enthusiasm, and insistence never do.

## Activation contract

Use this ordered state machine on every host:

`verified_load -> bounded_reconnaissance -> alignment_question -> explicit_handoff -> autonomous_dispatch`

Deep technical research requesting evidence and a decision-ready deliverable
triggers this contract. Ordinary explanation, small edits, one-shot answers,
and unrelated requests do not; negative triggers must not start
reconnaissance or dispatch. Before `explicit_handoff`, do not dispatch,
delegate, call external research, or write a final research artifact. Missing
or stale loader receipts, misalignment, unavailable resources, or an implicit
handoff return a bounded blocked disposition naming the failed phase and the
next safe action. Silence, "okay", or "continue" is not alignment evidence.

## Load bundled resources

- Resolve every relative path against the skill directory the host supplies.
  The installed package is read-only; keep run state in the writable
  workspace and persist a checkpoint before returning each response.
- Read `references/research-quality-playbook.md` before alignment or
  research: it carries the quality bars these protocols enforce.
- Read `references/alignment-controller.md` and initialize its run state
  before the first alignment question; run its `plan` immediately before
  every pre-handoff question and `record` after each response. Two unchanged
  fingerprints select reconnaissance instead of a repeated question.
- Use `assets/brief-template.md`, `assets/research-strategy-template.md`,
  `assets/technical-research-package-template.md`, and
  `assets/human-brief-template.md` for their corresponding artifacts.
- Read `references/blueprint-generation-research.md` only when forming or
  revising the Blueprint Target and Decision Map; read
  `references/product-contracts.md` only when exact persisted schemas matter.
- Read `references/research-tree-architecture.md` before initializing,
  expanding, pruning, or closing a tree. `references/debug-tracing.md` covers
  explicit diagnosis only: tracing is hook-only, sanitized, and never blocks
  research or target work.

## Python execution contract

When operating in a `research-tree` source checkout, run every bundled Python
script through the locked project environment: `uv run --frozen python ...`.
Discover the checkout containing `pyproject.toml` and `uv.lock` before
invoking the script, and use `uv run --project <checkout> --frozen python ...`
when the current working directory is elsewhere.
Never substitute the system `python` executable. If no `uv` project can be found, report an actionable
environment blocker instead of producing a parser-level error from an
incompatible Python.

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

## Protocol 1 — Elicitation and alignment loop

Treat every initial request as exploratory and materially incomplete until
reconnaissance says otherwise, even when it sounds specific. A vague, short,
or contradictory brief is a difficulty signal, not permission to invent
missing requirements.

- Inspect supplied material and the repository before asking anything
  detailed, and run bounded reconnaissance so each turn adds knowledge the
  requester did not have. Never answer an exploratory request with only a
  questionnaire, option table, plan, or research tree.
- Ask one open-ended, guided prompt at a time, answered in their own words.
  Do not use multiple-choice menus as the default discovery mechanism;
  structured input tools are transports for a rare discrete decision after
  open-ended guidance, never a substitute for it.
- No question-only turn: every turn mirrors the current understanding, names
  one consequential gap in the current context, adds the smallest useful
  evidence, and invites correction. Keep interactive turns under 1000
  characters and split work into short rounds (progress, new information,
  impact, one decision, next step). On confusion, missing vocabulary, or
  "I don't know", run a teaching reconnaissance cycle: inspect the smallest
  useful web, repository, or supplied sources, explain the result plainly,
  show one implication, then ask one guided question.
- Co-evolve cognition before strategy handoff: expose your reading,
  assumptions, strongest counterargument, and consequence if wrong; invite
  challenge; state what changed on both sides. Persist an alignment-turn
  record (mirror, gap, evidence, delta, decision effect) after each
  meaningful exchange. If no field changed, run reconnaissance instead of
  repeating the question. Intent understanding remains active throughout the round.

## Protocol 2 — Claims, feasibility, and cost

- Every user and agent technical assertion is a claim with provenance,
  evidence status, and consequence if wrong. Statuses: asserted, hypothesis,
  supported, refuted, unknown, superseded. Evidence levels: proposed,
  source-inspected, built, executed, independently-reviewed. Mark
  single-source claims unverified and keep contradictions visible.
- Classify constraints as hard, preference, aspiration, or estimate. Never
  silently relax a hard constraint and never reject the task because a
  negotiable aspiration is unmet. Human insistence does not make an
  infeasible combination feasible.
- Long-horizon research is cost-tolerant: never invent a monetary budget and
  never use API or token spend as a reason to narrow or stop. Operational
  guardrails (time slices, tool-call batches, concurrency, storage, safety,
  host limits) end a batch with a resumable checkpoint, never a final stop.
- Dispose feasibility explicitly: plausible, conditional, infeasible, or
  indeterminate. State infeasibility with the conflicting constraints, the
  relevant bound, and the nearest feasible reframings. Never silently
  substitute your preferred feasible alternative, and never declare
  impossibility from intuition: run the smallest feasibility spike that
  could change the disposition.

## Protocol 3 — Strategy lifecycle and goal wiring

The strategy handoff has two gates: a decision-equilibrium draft, then an
explicitly confirmed projection. Confirmation is the run's authoritative
goal, and everything downstream validates against it.

1. Propose. Draft outcome, decision targets, tracks, evidence expectations,
   autonomy envelope, and success oracles. Persist the draft with
   `research-tree strategy propose` when the checkout runtime is available;
   otherwise persist the equivalent intent in workspace artifacts.
2. Display. `research-tree strategy display` shows a projection only after
   the falsifiability review (`validate_falsifiability`) accepts it: every
   success oracle names evidence standards and every target reference
   resolves. Display is inspection, not acceptance.
3. Confirm. `research-tree strategy confirm` requires a confirmation that
   quotes the displayed digest; a bare "yes" is a rubber stamp and changes
   nothing. The downstream basis is `latest_confirmed`, fail-closed: draft,
   displayed, or superseded projections never count.
4. Compile Research Tree revision zero only after confirmation, from the
   Decision Map and existing Finding Packs.
   Do not create or display a Research Tree before this boundary. Every dispatched slot then carries
   its required `serves` link, validated against the confirmed projection;
   an invalid link rejects the slot.

### Autonomy envelope after strategy handoff

Declare once at handoff and then operate inside it: autonomous choices
(research, tools, delegation, intent and strategy revision within granted
authority); hard stop triggers (insufficient authority or safety boundary, a
missing capability, or an oracle that cannot be honestly evaluated);
continuation state persisted after every meaningful batch; the completion
oracle; and the failure policy (retry or replan recoverable failures, persist
a blocker with evidence, never silently downgrade the goal). If evidence
invalidates the strategy, create a successor revision internally and continue
without another approval.

## Protocol 4 — Assistance and correction protocol

The requester is authoritative about goals, never about truth.

- Error, ambiguity, or confused logic in the requester's input: do not
  silently obey and do not silently fix. Ask one Socratic clarification at a
  time (small steps over rounds, each restating what you heard), or derive
  the counterexample: "by the current oracle, evidence X is judged unmet."
- Insistence after clarification: warn the consequence concretely (which
  oracle goes unmet, which contradiction follows), then comply and record a
  waived goal-satisfaction verdict with an explicit waiver reason.
- Agent error: record the correction and revise intent, scope, or tree;
  never reduce it to a cosmetic report edit.
- Interruption (new ask, new information, correction): use `apply_correction`
  with a `CorrectionEvent` (kind exactly `correction` or `reopen`)
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts. Reordering only not-yet-dispatched work
  inside one round takes the lighter `record_same_round_replan` path instead.
- Contradicted delivery (by requester or new evidence): `apply_contradiction`
  with the finding refs and reason when the checkout runtime is available;
  otherwise persist the equivalent intent in workspace artifacts. Present the
  re-entry offer it produces instead of an improvised apology.
- After presenting both deliverables, collect exactly one of the
  `ACCEPTANCE_DECISIONS` (accepted, rejected, needs_deeper_research,
  needs_intent_correction, partially_accepted) via `DeliveryAcceptance` bound
  to the displayed digest. Silence or "okay" is not acceptance. User-visible
  status messages echo `research-tree status`
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts and answer from the persisted checkpoint.

## Protocol 5 — Dispatch and the slot-only contract

- Dispatch only the dependency-ready frontier after revision zero. Give each worker only the Decision Slot, its source boundary, stop condition, and Finding Pack schema.
- A worker MUST NOT receive the strategy projection digest, primary goal text, or other slots.
- Workers return atomic Finding Packs, not prose chapters. The coordinator
  owns contradiction checks, deduplication, coverage, Living Brief updates,
  and synthesis. Do not hand a broad track to one worker or let workers re-delegate;
  capacity left unused without a dependency, safety, duplicate,
  or capability reason is a conformance failure.
- A worker may report a blocker only after searching available sources and
  tools, inspecting local references or the repository, and trying safe
  alternatives; record the missing capability and evidence. "I don't know"
  by itself is not a blocker.
- Run the plan-to-execute loop: ingest a verified pack, then record its
  goal-contribution verdict (`assess_goal_contribution`). ADVANCES and
  PARTIAL count toward the slot; NO_CONTRIBUTION and CONTRADICTS leave the
  tree's consumed set untouched, trigger a same-round replan with the
  guidance defect named, and the second consecutive NO_CONTRIBUTION
  escalates to a method-switch consultation. Insight Digest signals
  uncovered, thin, contested, and qualified are successor-work triggers, not
  report-writing cues; only a converging slot advances to Decision Ledger
  review. Selection upweights failed validation and normalizes value by
  observed branch complexity; worker confidence is never an update signal.
- Reaching an operational guardrail creates a resumable checkpoint, not an
  automatic final stop. Continue until Decision Slot closure oracles pass;
  an empty static task list is not a stop condition.

## Protocol 6 — Delivery and completion gates

- Before any implementation, target edit, or irreversible experiment, emit an
  Alignment Checkpoint: goal and deliverable, scope and non-goals, authority
  and environment, success oracle, unresolved high-impact decisions, and
  feasibility. Do not act while a high-impact field is unknown or
  agent-selected.
- Never end a requested investigation after only showing a research tree,
  option table, diagnosis, or proposed fix list: return evidence-bearing
  progress in the same round (inspected sources, repository facts, a safe
  experiment, or a scoped feasibility result). "Recommendations only" means
  do not edit the target system; it never means skip the research.
- Deliver both artifacts or none: the Technical Research Package
  (repository-grounded, cited, honest evidence levels, ordered work with
  validation and rollback) and the Human Brief (decision-oriented language,
  what changed in each side's model, what was actually built or executed,
  what remains uncertain, next milestone). They must agree on scope,
  decisions, uncertainty, and evidence. An interim note is not the final
  report: while the Living Brief is still exploring or reopened, label the
  response interim and continue.
- Completion is gated per oracle: the coordinator registers a verdict via
  `write_goal_satisfaction` for every success oracle (satisfied or partial
  cites evidence that resolves to run artifacts; waived carries a waiver
  reason; unmet is explicit and never covers an oracle). While an oracle is
  uncovered the run cannot complete, and the blocker names
  `resolve:goal_satisfaction:<oracle_id>`. Do not report completion while
  the gate is blocked. Dissatisfaction, correction, or a depth objection
  reopens the Living Brief for a new evidence-bearing batch.

## Implementation boundary

Do not implement the researched product unless explicitly asked. Small safe
prototypes and experiments are research evidence. OpenSpec conversion is
optional and only on explicit request: preserve Living Brief revisions,
evidence anchors, conditional decisions, validation oracles, and unresolved
disagreements in it.
