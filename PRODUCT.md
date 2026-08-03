# Product Specification: research-tree

## Status

This document defines the target product. It supersedes the repository's prior
identity as a mandatory recursive evidence-DAG and frozen-report workflow. That
runtime has been removed; a future implementation must follow this
specification rather than revive its old state model.

## 1. Product Definition

`research-tree` converts incomplete project context into research-grounded
technical design that an implementation agent can use to ship quickly.

It is not primarily a generic deep-research product, a fixed questionnaire, a
business-planning assistant, or an automatic OpenSpec generator. Business,
product, and demo context can influence technical choices, but the product's
center of gravity is detailed technical research, design, and implementation
readiness.

### North-star outcome

After a research round, a capable implementation agent can understand the
current system, the research-backed technical direction, the change boundaries,
the important trade-offs, and a validated sequence of work without repeating
the original discovery process.

## 2. Actors

| Actor | Role |
| --- | --- |
| Requester | Supplies any amount of context, reviews outcomes when desired, and may introduce feedback or non-negotiable constraints. The requester is not assumed to have domain expertise. |
| Research Agent | Understands intent from context, inspects repositories, performs alignment and deep research, chooses a research strategy, and produces the two reports. |
| Implementation Agent | Consumes the Technical Research Package and optionally an OpenSpec change to implement and validate the work. |

The requester and Research Agent collaborate while the Intent Model and
Research Strategy are being formed. Once the strategy is selected, an explicit
control handoff gives the Research Agent full autonomy for execution,
replanning, delegation, and continuous intent correction within the granted
authority and environment. The requester is not a required participant after
that handoff.

## 3. Context Pack

The product accepts a heterogeneous context pack:

| Input | How it is used |
| --- | --- |
| Brief, idea, goal, or user-labelled bundle | Establishes an initial hypothesis, not a complete specification. A bundle may contain many materials. |
| Articles, links, notes, and drafts | Provide domain signals, claims to verify, language, constraints, and possible directions. |
| Code repository | Provides the baseline for behavior, integration, dependencies, tests, deployment, and change impact. |
| Logs, data, screenshots, or prior experiments | Provide operational facts and validation signals. |
| Prior research and feedback | Become context for a new Working Brief; they are never automatically inherited as truth. |

The Research Agent must distinguish observed facts, sourced external facts,
inferences, assumptions, and proposed choices. It must also distinguish a
user-provided brief from the internal **Working Brief**: the former may be one
document, a folder, a group of links, a repository plus notes, or no separate
artifact at all; the latter is the agent's current synthesis of selected
context.

Every input is recorded in an **Input Ledger**. A ledger entry preserves its
kind, origin, readable scope, content or revision identity, and the rounds that
used it. For a repository entry, record the local path or remote, branch and
commit when available, read-only scope, and the baseline reconnaissance result.
The ledger prevents a later round from silently treating a changed repository,
new article, or old report as the same input.

Inputs may be grouped into a **Context Bundle** when the requester supplies
them together. Preserve both the bundle membership and the individual entries:
the grouping communicates intent, while each material retains its own revision,
authority, scope, and possible contradictions. A bundle is not a claim that its
members agree or that all of them are equally authoritative.

## 4. Operating Model

```text
Context pack / Context Bundle
    |
    v
Context understanding and repository reconnaissance
    |
    +--> proportionate alignment research when needed
    |
    v
Intent Understanding / Intent Model
    |
    v
Working Brief + Research Strategy
    |
    v
Autonomous deep technical research
    |
    v
Technical Research Package + Human Brief
    |
    +--> explicit request only --> OpenSpec conversion
```

### 4.1 Intent understanding is a continuous product loop

The product's first job is not to extract keywords or turn user material into a
requirements form. It is to understand what the requester is trying to achieve
well enough to choose useful research and design work. A literal request, a
collection of articles, a repository, and a draft may each contain only partial
or even conflicting signals of that intent.

The agent creates a revisable **Intent Model** as soon as it has enough context
to state a useful hypothesis, but intent understanding never becomes a finished
pre-research phase. Repository inspection, alignment research, experiments,
external evidence, and requester feedback can all change the current reading.
The agent must repeatedly test the Intent Model while it researches, and must
revise the Working Brief, Decision Map, and active strategy when the evidence
changes the intended outcome, scope, authority, success definition, or a premise
that materially affects a user choice.

The Intent Model separates:

- observed statements and repository facts from inferences about intent;
- intended technical outcome from the material used to describe it;
- success signals and decision drivers from implementation ideas;
- hard constraints and non-goals from preferences or hypotheses; and
- leading and viable alternative intent interpretations, their evidence,
  confidence, and the consequence of choosing the wrong one.

Decision drivers can be technical, user, delivery, commercial, risk, or another
dimension surfaced by the Context Pack. The product does not assume that a
business analysis is required, but it must preserve such a driver when it
changes technical architecture, scope, or validation.

The Intent Model is neither a mandatory questionnaire nor a frozen intent
contract. The agent may form and test hypotheses through repository inspection,
bounded alignment research, and deep technical research itself. It asks the
requester only during the pre-strategy collaboration phase when consequential,
non-recoverable choices differ across viable intent interpretations and the
available material and research cannot responsibly rank them.

### 4.2 No mandatory dialogue gate

The previous product stopped before any online research until an intent contract
was completed. This is the wrong behavior. The agent may need to inspect the
web, supplied material, or repository first to understand the request well
enough to form a useful strategy.

Before the Research Strategy is selected, the agent proceeds using best
judgment. It asks only when:

- the requester asks to explore interactively;
- a decision is consequential and non-recoverable; and
- available context, repository facts, and bounded alignment research cannot
  establish a responsible assumption.

Questions must be minimal and decision-bearing, never a way to offload research
back to the requester.

### 4.3 Alignment research

Alignment research is small, reversible research that improves the agent's
intent understanding before it commits to a deep research strategy. It can cover
unfamiliar terminology, claims in supplied articles, relevant standards,
existing products, current ecosystem facts, or referenced libraries.

It is allowed during optional co-exploration and before autonomous deep
research. It can test a high-impact Intent Model hypothesis, for example whether
the supplied material implies a technical feasibility problem, a deployment
constraint, a target user workflow, or a commercial driver. It must not silently
become a full research run or lock the user into a direction.

### 4.4 Autonomous deep research

Once the Research Strategy exists, control is handed to the Research Agent. It
owns normal uncertainty, does not freeze the Intent Model, and does not return
ordinary research decisions to the requester. It researches, compares
alternatives, tests where possible, records assumptions and validation work,
and performs an intent review after each meaningful evidence batch. If evidence
changes the target or invalidates the strategy, the agent creates a successor
Intent Model, Working Brief, and Strategy revision internally and continues
within the granted authority. It does not reopen collaborative questioning just
because its own understanding changed.

## 5. Intent Model, Working Brief, and Research Strategy

### 5.1 Intent Model

The Intent Model is the primary interpretation artifact. It records the
available intent signals, leading and viable alternative readings, desired
outcome, success signals, decision drivers, constraints, non-goals, ambiguity,
and what evidence or user answer would change the interpretation. It must point
back to Context Bundle members, repository observations, and alignment research
instead of presenting an inferred goal as a verbatim user requirement.

An Intent Model can be partially unresolved and is revised throughout the round.
The agent branches internally or adds intent-validation work whenever an
ambiguity is recoverable. It does not require every ambiguity to be resolved
before it begins technical research, and it must not treat the first model as
permission to ignore later evidence.

### 5.2 Working Brief

A **Working Brief** is the strategy-ready snapshot of the current Intent Model.
It is a traceable synthesis of one or more Context Pack inputs, not a synonym
for a single user message or file. It should capture:

- one or more current triggers: request, feedback, newly supplied material, or
  repository change;
- the selected Context Bundle and individual input ids, including the role of
  each item (`primary`, `constraint`, `context`, `counterexample`, or
  `out_of_scope`);
- the Intent Model revision and the leading interpretation it carries forward,
  plus material alternatives that remain viable;
- the current interpretation of the desired technical outcome and implementation
  boundary;
- observed repository baseline and explicitly retained hard constraints;
- material conflicts, ambiguity, assumptions, and risk; and
- parent-round references when this is a follow-up.

The Working Brief preserves disagreement instead of silently blending multiple
articles, drafts, and repositories into a fictitious consensus. It may include
agent-formed hypotheses, but labels them as such. It is not a frozen
requirements form; it is a compact, revisable entry point for selecting a
strategy.

### 5.3 Research Strategy

The Research Strategy is the core product decision. It determines:

| Field | Meaning |
| --- | --- |
| Technical outcome | What technical decision or production capability the round must enable. |
| Intent basis | The Intent Model revision, interpretation, drivers, and unresolved alternatives that shape the strategy. |
| Baseline | Relevant repository facts, material observations, constraints, and assumptions. |
| Research tracks | Prioritized technical areas to investigate. |
| Decision value | Why each track can change the recommended design or implementation plan. |
| Method | Repository analysis, primary documentation, implementation experiments, benchmarks, standards, or other appropriate evidence. |
| Depth and exit criteria | How much research is needed before a design choice is actionable. |
| Delivery boundary | Technical Research Package and Human Brief, plus optional OpenSpec conversion if explicitly requested. |
| Autonomy policy | Assumptions the agent will carry and rare circumstances that justify a user question. |
| Prior-material disposition | For each relevant prior item: `reuse`, `revalidate`, `downgrade`, `ignore`, or `overturn`. |

Typical tracks include system architecture, agent workflow, tool selection,
security and permissions, performance, data and state management, evaluation,
deployment, observability, migration, and failure recovery. The strategy must
select only tracks relevant to the current Working Brief.

If the requested depth or time is unspecified, use a bounded operational
guardrail and disclose the unvalidated remainder. Do not invent a monetary cap
or block only because the requester did not provide one; financial cost is
non-gating unless explicitly supplied as a constraint.

### 5.4 Blueprint Target and Decision Map

Before deep research, the agent compiles a bounded **Blueprint Target** from
the Intent Model, Working Brief, selected material, and repository baseline. It
is the set of design obligations that must be closed before an implementation
agent can begin. It is not a questionnaire, a report outline, or a frozen
requirements contract.

The target includes only obligations relevant to the Working Brief and its
selected Context Pack, such as:

- architecture and technology choices with material consequences;
- component responsibility, interface, data, state, and failure boundaries;
- security, permissions, deployment, performance, and operational controls;
- repository change surfaces, migration, compatibility, rollout, and rollback;
- tests, experiments, acceptance oracles, observability, and unresolved risk.

Each obligation is represented by a **Decision Slot** in a Decision Map. A slot
records the decision question, constraints and repository anchors, viable
alternatives, impact, uncertainty, irreversibility, downstream dependencies,
evidence standard, validation method, and closure rule. Research may change the
map when it discovers a missing design obligation; it must record that change
rather than silently adding a report section.

The Strategy turns open Decision Slots into research tracks and work items. A
track is therefore an execution grouping, not the unit of convergence. The
convergence unit is a technical decision that is selected, conditionally
selected with a validation task, or explicitly deferred.

## 6. Repository-First Technical Design

When a repository is included, the agent must inspect the real system before
making an implementation recommendation. The repository baseline should cover
the relevant behavior, paths/symbols, interfaces, data/state flow, dependencies,
test suite, deployment configuration, and compatibility constraints.

The package must tie external findings to actual implementation locations. For
example, a recommendation to use a framework, protocol, or model is incomplete
until it identifies the integration boundary, replacement surface, tests, and
operational effects in the supplied repository.

If no repository exists, the agent may make greenfield assumptions, but must
label them and define how an implementation agent should validate them.

## 7. Deliverables

### 7.1 Technical Research Package

The agent-facing package is the primary deliverable. It contains, as relevant:

1. Round identity, scope, non-goals, hard constraints, and relationship to
   earlier rounds.
2. Intent basis: leading interpretation, material alternatives, decision
   drivers, and assumptions that materially shape the design.
3. Current technical baseline from repository and supplied material.
4. Research strategy, research tracks, findings, source quality, and technical
   implications.
5. Recommended architecture: components, responsibilities, interfaces,
   data/state flows, agent/tool loop, permissions, safety boundaries, and
   deployment topology.
6. Technical decision records: rationale, alternatives, consequences, intent
   basis, and
   conditions that would reverse a choice.
7. Implementation plan: ordered work, repository touch points, dependencies,
   tests, evaluation, observability, rollout, migration, and rollback.
8. Unknowns, assumptions, risk register, and targeted validation experiments.
9. Traceability to intent hypotheses, repository locations, supplied material, external sources,
   and prior rounds.

This package is compiled from a **Decision Ledger**, not stitched from worker
reports. Each consequential decision records its alternatives, evidence and
repository anchors, selected option, design consequence, change surface,
validation or acceptance oracle, uncertainty, and reversal condition. The
package must include a Blueprint Closure view that tells an implementation
agent which Decision Slots are selected, conditional, deferred, or blocked.

This package is not a prose-only report. Its job is to eliminate unnecessary
rediscovery for the implementation agent. A recommendation without a concrete
repository boundary or an explicitly labeled greenfield assumption is not a
blueprint element.

### 7.2 Human Brief

The human-facing output is separate. It explains what the agent understood,
the recommended technical direction, expected capability, consequential
trade-offs, important change from the prior result, and current risk. It is not
a compressed copy of the technical package.

### 7.3 Optional OpenSpec conversion

OpenSpec generation happens only when requested. The Technical Research Package
maps to the standard OpenSpec flow:

| Research-package material | Optional OpenSpec artifact |
| --- | --- |
| Problem, scope, capability, and impact | `proposal.md` |
| Behavioral requirements and acceptance cases | `specs/` |
| Architecture, decisions, alternatives, risks, migration | `design.md` |
| Ordered implementation and validation work | `tasks.md` |

For a repository-backed round, these are delta artifacts against the observed
system. The mapping follows OpenSpec's `proposal -> specs -> design -> tasks`
workflow. [OpenSpec schema](https://github.com/fission-ai/openspec/blob/main/schemas/spec-driven/schema.yaml)

## 8. Feedback Is Recursive Research

User feedback starts a new Working Brief, not a patch to the previous report:

```text
feedback + full available context
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

The new strategy chooses the role of earlier material independently for every
round: reuse, revalidate, downgrade, ignore, or overturn. It may also regroup
or split earlier Context Bundles when their members have different relevance.
Prior approval or silence is not proof of current relevance. Only an explicitly
retained hard constraint is automatically carried forward.

Feedback received while a round is still running becomes an input at the next
safe checkpoint. Before strategy handoff, it participates in collaboration and
may change the selected strategy. After handoff, the agent incorporates it
autonomously, marks the affected round or strategy revision as superseded when
needed, and continues without waiting for another approval. Completed work
remains traceable candidate context.

When the requester rejects the overall direction, the agent starts a new root
Working Brief. Otherwise it retains provenance so the new package can explain
which earlier conclusions still matter and why.

## 9. Quality Bar

The result is complete only when:

- a capable implementation agent can begin without rediscovering the design;
- every high-impact Decision Slot is selected, conditionally selected with a
  concrete validation task, or explicitly deferred with a fallback;
- the leading Intent Model interpretation and any material alternative are
  visible, with their design consequences;
- recommendations are tied to repository reality or clearly labeled greenfield
  assumptions;
- each important finding has an explicit technical implication;
- each consequential decision has alternatives, traceability, a validation
  oracle, and a reversal condition;
- implementation work has dependencies and verification, not only headings;
- unknowns are converted into assumptions, risks, or validation tasks;
- the Human Brief is intelligible without reading the agent package; and
- OpenSpec artifacts appear only when explicitly requested.

The following are insufficient on their own: a source list, an architecture
diagram without integration detail, a generic market summary, a long
questionnaire, a report that omits a buildable path, source-count targets, or a
test suite that has not been checked for relevance and coverage.

## 10. Target Algorithm and Architecture

The research behind this section is recorded in the [Blueprint Generation
Package](references/blueprint-generation-research.md). Its central conclusion
is that the product must converge on technical decisions and implementation
readiness, not on a completed evidence tree or a long report.

### 10.1 Decision-Centric Adaptive Research Loop

The product-level recursive unit remains a **Working Brief round**, not an
evidence node:

```text
Context Bundle or feedback -> Intent Model N -> Working Brief N -> Strategy N -> Research Round N -> artifacts
                                                                     ^
                                                                     |
                                                       feedback creates Intent Model N+1
```

Within a round, the agent follows a Decision-Centric Adaptive Research Loop:

```text
Context + repository baseline
             |
             v
Intent Understanding / Intent Model
             |
             v
       Working Brief
             |
             v
Blueprint Target / Decision Map
             |
             v
 Strategy compiler + dynamic work portfolio
             |
             v
 independent research tasks run in parallel when safe
             |
             v
       Finding Packs -> intent review -> Decision Ledger -> replan or converge
             |
             v
 Blueprint compiler -> readiness verification -> two deliveries
```

The first pass is deliberately broad: repository reconnaissance, technical
landscape, viable options, and major risks for high-impact Decision Slots. The
next passes go deep only where evidence can change an architectural choice or
unblock implementation. This avoids both early fixation and exhaustive research
of low-value details.

A first implementation may use this explainable heuristic to prioritize a
ready work item:

```text
priority = (decision_impact * uncertainty * downstream_leverage
            * irreversibility * expected_information_gain)
           / (estimated_cost + duplicate_risk)
```

This is a scheduling heuristic, not a claimed universal optimum. Start with
explicit low/medium/high estimates and record outcomes. Only calibrate it toward
learned or value-of-information scheduling after real rounds provide enough
data to assess prediction quality.

The coordinator replans within the same round when high-quality evidence
conflicts, a repository fact falsifies an assumption, a prototype fails, a
critical Decision Slot is uncovered, a task proves redundant, or the remaining
budget cannot change a choice. Normal replanning is autonomous. Feedback that
changes the target, priority, or success definition supersedes the round and
creates a new Intent Model and Working Brief.

### 10.2 Work Items, Findings, and Decisions

A **Research Track** is only an execution grouping. The scheduler creates
small Work Items that each answer one Decision Slot under an explicit boundary:

- decision question, repository scope, dependencies, and expected design
  impact;
- preferred methods, source standard, tool permissions, and budget;
- alternatives to investigate and duplicate-work exclusions;
- completion rule and structured Finding Pack schema.

Workers do not return unstructured mini-reports. A Finding Pack contains atomic
observations; source, input, or repository anchors; applicability conditions;
confidence and limitations; support or contradiction of options; implementation
implications; and remaining uncertainty.

The coordinator folds Finding Packs into a **Decision Ledger**. Every
consequential record contains the selected option, meaningful alternatives,
constraints, supporting and conflicting evidence, repository touch points,
design consequence, acceptance oracle, uncertainty, fallback, and reversal
condition. The Technical Research Package is compiled from this ledger.

### 10.3 Graph Boundaries

The product does not restore a global recursive evidence DAG. It has distinct
data structures with deliberately limited responsibilities:

| Layer | Structure | Purpose | Rule |
| --- | --- | --- | --- |
| Intent Model and Working Brief history | Immutable lineage | Relate feedback, Context Bundles, interpretations, and rounds | `supersedes` creates a new interpretation and Working Brief, never mutates history. |
| Current execution | Rebuildable work-dependency DAG | Schedule ready work and parallelism | Acyclic per scheduling batch; discarded or rebuilt when strategy changes. |
| Evidence and facts | Typed provenance relation graph | Link sources, repository facts, claims, conflicts, and updates | May contain support, contradiction, and supersession cycles. |
| Design to delivery | Decision-to-implementation graph | Link decisions to interfaces, changes, tests, and rollout | Allows alternatives and reversal relationships; the final work plan may be a DAG. |

This separation preserves traceability without forcing dynamic research,
contradictions, or feedback into a single one-way tree. Local search or
branching may still be useful for a narrow, high-cost decision with explicit
candidate options and an evaluable outcome; it is not the global research
algorithm.

### 10.4 Product Architecture

```text
Input Registry / Context Inventory / Repository Inspector
                         |
                         v
      Context Facts + Intent Modeler + Blueprint Target Compiler
                         |
                         v
Intent Model / Working Brief / Strategy / Decision Map / Round Store
                         |
                         v
              Adaptive Portfolio Scheduler
                         |
       +-----------------+------------------+----------------+
       v                 v                  v                v
  external research  repository analysis  prototype/spike  evaluation
       \                 |                  |                /
        \----------------+------------------+---------------/
                         v
            Finding Store + Provenance + Decision Ledger
                         |
                         v
          Blueprint Compiler + Readiness Verifier
                         |
             +-----------+-----------+
             v                       v
Technical Research Package       Human Brief
             |
             +--> explicit request --> OpenSpec Exporter
```

The `Intent Modeler`, `Blueprint Target Compiler`, `Decision Ledger`, `Adaptive
Portfolio Scheduler`, and `Readiness Verifier` are first-class components. They must not
be aliases for the retired intent contract, global workspace state, or
frontier-ranking helper. A source-provenance or high-assurance review adapter is
strategy-selected when appropriate; it is not the top-level state machine.

### 10.5 Readiness Verification and Evaluation

Completing a report is not completion. The verifier applies these gates:

1. **Intent alignment:** the leading Intent Model interpretation, explicit
   user statements, and material alternatives remain traceable to the design
   choices they affect. This tests transparent interpretation, not access to a
   user's private mental state.
2. **Decision closure:** every P0/high-impact Decision Slot is selected,
   conditionally selected with a concrete validation task, or deferred with a
   fallback. Unowned `TBD` values fail the gate.
3. **Traceability:** each consequential decision links to applicable repository
   facts, supplied context, external evidence, or an explicit assumption, then
   to a design element, change task, and acceptance oracle.
4. **Repository fit:** path, symbol, interface, revision, test, and deployment
   anchors resolve against the inspected baseline. Greenfield assumptions are
   clearly isolated.
5. **Implementation readiness:** an independent implementation agent receives
   only the repository baseline and package. It must identify the first slice,
   touch points, interfaces, validation, and blockers without redoing research.
   A rediscovery question becomes a package defect or a targeted work item.
6. **Operational quality:** a rubric assesses coherence, security, migration,
   observability, performance, rollout, rollback, source quality, and efficient
   tool use. Representative human review calibrates automated judging.

Verification cost scales with risk. Default rounds use structural and anchor
checks. Medium-risk rounds add a bounded spike or narrow implementation slice.
High-risk or production-ready rounds add isolated implementation, independent
acceptance and regression testing, and operational rehearsal. Existing tests
are signals, not unquestioned proof: their relevance and coverage may require
an independent audit.

### 10.6 Storage and Safety Boundaries

New rounds require run-scoped storage and immutable lineage. A single global
`RESEARCH_WORKSPACE/research_state.json` cannot safely represent recursive or
parallel rounds. Store versions of context facts, Intent Models, Working Briefs,
Decision Maps, work batches, Finding Packs, Decision Ledger entries, compiled
packages, and readiness results so a later Working Brief can choose what to
reuse or revalidate.

Repository ingestion is read-only by default and must enforce path boundaries,
symlink handling, secret exclusion, binary and size limits, and revision
recording before material enters the Input Ledger. Prototypes and implementation
readiness runs require an isolated, explicitly scoped execution environment.

## 11. Implementation Sequence

The prior runtime and its mandatory workflow have been removed. Its source code
and tests remain available through repository history for reference, but they
are not a compatibility target.

Build the new product in this order:

1. Add durable Input Ledger, Context Bundle, Intent Model, Working Brief, round,
   strategy, feedback-lineage, and run-scoped storage concepts independent of
   any old state model.
2. Add repository reconnaissance and context facts with revision, path, secret,
   symlink, binary, and size controls; then add intent-understanding operations
   that link those facts and supplied materials to revisable hypotheses.
3. Add the Blueprint Target, Decision Slot, and Decision Ledger contracts plus
   deterministic structural and traceability validation.
4. Add a strategy compiler that converts Decision Slots into bounded research
   tracks and work-item contracts.
5. Add the adaptive portfolio scheduler, batch dependency graph, Finding Pack
   ingestion, conflict detection, and event-driven replanning.
6. Add a blueprint compiler that renders the two target artifacts from the
   Decision Ledger, including repository change surfaces and validation work.
7. Add risk-tiered readiness verification and a small real-world evaluation set
   that compares the adaptive loop with simpler baselines.
8. Add an explicit OpenSpec export adapter that produces repository deltas.
9. Add source acquisition, provenance integrity, or high-assurance review only
   when a strategy explicitly selects them.
