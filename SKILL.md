---
name: research-tree
description: Turn incomplete project context into an agent-actionable technical research package and a human brief. Choose a research strategy from the available context, research autonomously, and create OpenSpec artifacts only when explicitly requested.
---

# research-tree

## Purpose

`research-tree` is a technical research and blueprint accelerator for agents.
It does not assume that the requester can state a complete problem, knows the
right technical questions, or can distinguish relevant from irrelevant prior
material.

Its first task is **intent understanding**: infer and test what outcome the
requester is trying to enable from the available Context Pack, while separating
literal material content from the agent's hypotheses about intent.

Use it to transform a context pack into two outputs:

1. A **Technical Research Package** that an implementation agent can use to
   design and build the work.
2. A **Human Brief** that explains the direction, key choices, expected result,
   and material uncertainty in decision-oriented language.

OpenSpec conversion is optional and happens only when the requester explicitly
asks for OpenSpec artifacts.

## Product Rules

- Do not force a questionnaire or continuous conversation. The default is to
  form a strategy and research autonomously.
- Do not ask the requester for facts that can be learned from supplied
  materials, a repository, or proportionate external research.
- Treat intent as a revisable model, not as the literal text of one message or
  document. Preserve multiple viable interpretations when they would lead to
  materially different research or design choices.
- Do not convert an inferred motive, market, user, or technical preference into
  a user requirement without an input anchor or an explicit hypothesis label.
- Use lightweight external research before strategy selection when it is needed
  to understand unfamiliar material, current terminology, a referenced product,
  a framework, or the surrounding technical landscape.
- Once a Research Strategy is selected, do not interrupt deep research with
  routine questions. State assumptions, branch internally, or add validation
  tasks instead.
- Ask one focused question only when a consequential, non-recoverable decision
  cannot be inferred safely, or when the requester explicitly wants a
  collaborative exploration mode.
- Treat feedback as an input to a new Working Brief and a new research round,
  not as an instruction to cosmetically edit the previous report.
- Prior findings are candidate context. Reuse them only when the new strategy
  judges them relevant; otherwise revalidate, downgrade, ignore, or overturn
  them.
- Produce concrete technical design consequences, not a generic research
  summary.

## Inputs

Accept any combination of the following as a **context pack**:

- a sentence, idea, or goal;
- articles, links, notes, screenshots, transcripts, or drafts;
- an existing code repository, including source, configuration, tests, docs,
  CI, issue history, and logs;
- prior research outputs and user feedback;
- explicit constraints such as time, deployment, safety, cost, compatibility,
  or delivery requirements.

Treat user-provided material as evidence and signals, not as a complete or
authoritative specification. Extract what it suggests, what it does not prove,
and which technical choices it may affect.

Do not equate a user-provided "brief" with one Input Ledger entry. A brief may
be a single sentence, a set of articles and drafts, a folder, a repository plus
notes, or an explicitly grouped collection of any of these. Preserve the
requester's grouping as a Context Bundle while recording its members separately.
The internal Working Brief is a strategy-ready snapshot of an Intent Model over
selected inputs, not a renamed copy of one material.

Maintain an Input Ledger for the round. For each entry record its kind, origin,
readable scope, revision or content identity, and relationship to the round. A
repository entry must include its path or remote, branch/commit when available,
read-only scope, and reconnaissance baseline. Do not silently reuse a changed
repository or an old research artifact as if it were the same input.

When materials conflict, retain their distinct anchors and record the conflict,
scope difference, or uncertainty. Do not merge them into a synthetic user
requirement merely because they arrived in the same bundle.

## Execute a Research Round

### 1. Establish the working context and understand intent

Read the supplied material and inventory the available inputs. When a code
repository is in scope, inspect it before proposing architecture:

- identify the relevant entry points, behavior, modules, interfaces, data and
  state flows, dependencies, tests, deployment path, and change surface;
- distinguish observed repository facts from assumptions;
- use repository paths and symbols in the Technical Research Package where they
  materially affect implementation;
- do not invent a greenfield system when an existing integration context is
  available.

Before selecting deep research, form an **Intent Model** from the Context Pack.
For each important interpretation, record:

- the desired outcome, success signal, decision driver, constraint, or non-goal
  it proposes;
- the input, repository observation, or alignment finding that supports it;
- confidence, authority boundary, and viable alternatives;
- the technical or product consequence if the interpretation is wrong; and
- whether research, repository inspection, a prototype, or a user question can
  resolve it.

The model must distinguish what the requester explicitly said from what the
agent inferred. Commercial, user, delivery, risk, or technical drivers are
included only when the Context Pack makes them relevant; none is a mandatory
dimension. Do not require full certainty: carry a recoverable ambiguity into
the strategy or test it with bounded alignment research.

### 2. Perform alignment research when useful

Before committing to a strategy, perform a bounded external search when it
improves understanding of the context. Typical reasons include unfamiliar terms
or products, stale claims, relevant standards, current library behavior,
competitors that imply a technical constraint, or existing open-source
solutions.

This is **alignment research**, not a hidden full research run. Use it to form
better technical and intent hypotheses, test high-impact interpretations, and
avoid asking avoidable questions. Clearly separate sourced facts from early
inferences.

### 3. Create the Intent Model, Working Brief, and Research Strategy

Complete or revise the **Intent Model** after context and alignment work. It
contains leading and viable alternative interpretations, desired outcomes,
success signals, decision drivers, hard constraints, non-goals, unresolved
ambiguity, input/repository anchors, and a consequence for each material
uncertainty. It is not a mandatory intent contract.

Then create a new **Working Brief** as the strategy-ready snapshot of the
Intent Model. It records one or more triggers, selected Context Bundle and
input ids, each input's role, the leading interpretation and viable
alternatives, explicit hard constraints, material conflicts, and the
relationship to earlier rounds. It must not blindly inherit earlier conclusions
or treat one supplied document as authoritative over the rest without a reason.

Then choose a **Research Strategy** that includes:

- the technical outcome and implementation decision it must enable;
- the Intent Model revision and interpretations that shape its scope, including
  any ambiguity that should remain open or be tested;
- the repository facts and user material that define the current baseline;
- a Blueprint Target and Decision Map: the bounded technical decisions that
  must close before an implementation agent can start;
- prioritized research tracks, such as architecture, agent workflow, tooling,
  safety, performance, data, deployment, evaluation, or migration;
- the question or decision each track resolves and why it matters;
- the necessary research depth, source types, and exit criteria for each track;
- the expected minimum viable technical loop and the path from it to production;
- assumptions the agent will carry without interrupting the requester;
- the requested deliverables, including whether OpenSpec conversion is wanted.

The strategy may be shown to the requester when they ask to co-explore. In the
default mode, it is an internal operating decision and research begins without
requiring approval.

If depth, time, or cost is unspecified, choose a bounded default budget and
state what remains unvalidated. Missing budget information is not by itself a
reason to stop.

The Blueprint Target is not a questionnaire or a report outline. It contains
only design obligations relevant to the Intent Model, Working Brief, and
selected Context Pack: high-impact architecture choices, interfaces, state and
failure semantics, security and operational boundaries, repository change
surfaces, validation, migration, and rollout. Each Decision Slot records the
intent interpretation it serves, impact, uncertainty, irreversibility,
alternatives, repository anchors, evidence standard, and its closure rule.

Tracks organize execution; a Decision Slot is the convergence unit. An open
high-impact slot must not disappear merely because a track has emitted a report.

### 4. Research autonomously

Perform the selected technical research without repeatedly asking the requester
to resolve normal uncertainty. Research must answer design decisions, not merely
collect sources. For each consequential conclusion, retain:

- the finding or repository observation;
- its technical implication;
- confidence, limitation, or transfer boundary;
- alternatives considered;
- the resulting design choice or validation task.

Start broadly across independent high-impact Decision Slots, then spend deeper
research on choices that remain uncertain and can change the blueprint. A Work
Item must be bounded to one decision question, scope, dependency set, source or
tool method, budget, expected Finding Pack, and completion rule. Run only truly
independent Work Items in parallel; serialize decisions that determine an
interface, repository boundary, or later experiment.

Workers return Finding Packs, not standalone report chapters. A Finding Pack
contains atomic observations, source/input/repository anchors, applicability,
limitations, option effects, implementation implications, and remaining
uncertainty. Fold it into a Decision Ledger that records every selected,
conditional, deferred, or blocked choice with alternatives, anchors, change
surface, validation oracle, fallback, and reversal condition.

Replan the current work portfolio when critical evidence conflicts, a repository
fact falsifies an assumption, a prototype fails, a high-impact Decision Slot is
uncovered, a task becomes redundant, or remaining budget cannot change a
choice. This is normal same-round research behavior, not a reason to ask the
user or start a new Working Brief.

Scale the research depth to implementation risk. Use multiple independent
sources, experiments, repository inspection, or prototypes where the choice is
high impact. Preserve source references sufficiently for an implementation
agent to revisit the decision.

The strategy may change during a round when evidence materially changes the
technical decision. Record the reason, affected tracks, and budget impact. This
is an internal strategy adjustment. A user feedback event that changes the
target, priority, or success definition is different: mark the active round
`superseded` at a safe checkpoint and create a new Working Brief instead of silently
continuing the old round.

### 5. Produce the two deliveries

#### Technical Research Package

Write a detailed, agent-facing package with these sections where applicable:

1. **Round and scope**: current Working Brief, scope, non-goals, and explicit
   constraints.
2. **Intent basis**: leading Intent Model interpretation, viable alternatives,
   decision drivers, source anchors, and material ambiguity that shapes design.
3. **Current baseline**: relevant repository behavior, paths, interfaces,
   tests, operational constraints, and supplied-material observations.
4. **Blueprint closure**: Decision Slots and their `selected`, `conditional`,
   `deferred`, or `blocked` status, including fallbacks.
5. **Research strategy and findings**: research tracks, sources, findings,
   confidence, and technical implications.
6. **Recommended technical design**: architecture, components, interfaces,
   data/state flow, agent/tool workflow, security boundaries, and deployment
   model.
7. **Decision Ledger**: selected approach, rejected or deferred alternatives,
   intent basis, anchors, consequences, validation oracles, and reversal
   conditions.
8. **Implementation plan**: ordered technical work, integration points,
   dependencies, validation, observability, migration, rollback, and production
   hardening.
9. **Unknowns and validation**: assumptions, risks, experiments, evaluation
   criteria, and conditions that would change the recommendation.
10. **Readiness record**: intent alignment, decision closure, traceability,
    repository fit, independent implementation-readiness, and operational-
    quality gates.
11. **Traceability**: intent hypotheses, sources, repository references, and
    relationship to prior rounds.

The package must let a capable implementation agent begin work without having
to rediscover the problem or reverse-engineer the reasoning.

#### Human Brief

Write a separate, concise explanation for the requester. Focus on:

- what the agent inferred from the current context, including the few material
  assumptions or viable alternatives that materially change the direction;
- the recommended technical direction and expected capability;
- the few decisions and trade-offs that matter to a human reader;
- meaningful changes from a prior round;
- the practical next milestone and material risks or uncertainty.

Do not turn the Human Brief into a shortened dump of component contracts,
source ledgers, or task graphs.

## Optional OpenSpec Conversion

Generate OpenSpec artifacts only on explicit request. Use the Technical Research
Package as the upstream design evidence, then create the requested subset of:

- `proposal.md`: why the change is needed, what changes, capabilities, and
  impact;
- `specs/`: behavioral requirements and scenarios;
- `design.md`: context, goals/non-goals, decisions, alternatives, risks,
  migration, and open questions;
- `tasks.md`: trackable implementation and validation work.

When a repository exists, produce deltas against its current behavior rather
than a greenfield spec. Do not create OpenSpec artifacts merely because the
research package mentions implementation tasks.

## Feedback and Recursion

When the requester responds to a result, create a fresh Intent Model and
Working Brief from the new feedback plus the selected Context Pack:

```text
new feedback + selected Context Bundles + repository + prior outputs
                              |
                              v
                        new Intent Model
                              |
                              v
                        new Working Brief
                              |
                              v
                     new Research Strategy
                              |
                              v
                       new research round
```

The feedback may make previous research irrelevant even when it was previously
accepted or unchallenged. Let the new strategy decide whether each earlier item
is reused, revalidated, downgraded, ignored, or overturned. Carry forward only
explicitly retained hard constraints. Start a new root Working Brief only when the
requester rejects the overall direction or supplies a clearly independent goal.

## Completion Standard

The round is complete when the Technical Research Package contains enough
grounded design detail for an implementation agent to act, its Intent Model
interpretation and material alternatives are traceable, every high-impact
Decision Slot has a disposition, and risk-proportionate readiness verification
has passed or is explicitly deferred with a fallback. The Human Brief must
communicate the direction without requiring technical reconstruction. A source
list, generic architecture diagram, broad market summary, completed task list,
or long report alone is not a complete result.

## Implementation Boundary

The previous Python evidence-DAG/reporting runtime has been retired. Do not
assume old commands, state files, snapshots, or report builders exist. A future
high-assurance source or provenance adapter may be added only as an explicit
strategy-selected component; it must not reintroduce mandatory clarification,
recursive-frame, freeze, or chapter-report behavior.
