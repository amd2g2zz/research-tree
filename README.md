# research-tree

`research-tree` is a strategy-driven technical research and blueprint skill. It
turns incomplete project context and large-scale research into the grounded
technical blueprint an implementation agent needs to ship quickly.

The input can be a short idea, a collection of articles, notes, drafts, links,
an existing code repository, test failures, or feedback on an earlier result.
The user is not expected to know the correct research questions, architecture,
or implementation path.

A user-provided brief is not assumed to be one document. It can be a grouped
Context Bundle containing any number of materials, including a repository. The
agent preserves each material and its revision separately, then creates a
traceable Working Brief that records which inputs are primary, constraints,
context, or counterexamples. Conflicting materials remain visible rather than
being silently combined into a fictional requirement.

More importantly, the agent performs **Intent Understanding** before choosing a
research strategy. It creates a revisable Intent Model that distinguishes user
statements from inferred outcomes, success signals, drivers, constraints,
non-goals, and viable alternative readings. A Working Brief is the
strategy-ready snapshot of that model, not the intent-understanding process
itself.

> Product status: this repository ships an implemented, composable Python
> runtime for persisted research-round artifacts and their workflow services.
> It is not a standalone autonomous-research CLI: source acquisition, research
> decisions, and production sandbox adapters remain explicit caller-owned work.

## First Runtime Path

The runtime uses an explicit run-store root. It never infers a workspace or
persists state somewhere else, so retain the same path to recover a round after
a process restart.

```powershell
git clone https://github.com/amd2g2zz/research-tree.git
cd research-tree
uv sync

$store = Join-Path $PWD ".research-tree-demo"
uv run python -m research_tree --help
uv run python -m research_tree create-round --store $store --round-id round-first
uv run python -m research_tree show-round --store $store --round-id round-first
```

The final `show-round` command is the recovery/readback path: run it again with
the same `--store` and `--round-id` to reconstruct the persisted round. Creating
that id again is rejected rather than overwriting the existing state.

## Runtime Boundaries

The `research-tree` CLI is round-management only. It supports `create-round`
and `show-round`; it does not ingest material, choose a strategy, collect
sources, or compile a complete technical handoff.

Use the public `research_tree` Python API for the composed workflow. It exports
`RunStore`, `InputIntakeService`, `IntentModelCompiler`,
`WorkingBriefCompiler`, `BlueprintTargetCompiler`, `DecisionLedgerCompiler`,
`DeliveryCompiler`, `ReadinessVerifier`, `FeedbackRoundService`, and explicit
OpenSpec/evaluation adapters. The public export surface is in
[`research_tree.__init__`](src/research_tree/__init__.py); the end-to-end test
shows the composed delivery, readiness, evaluation, and opt-in export route in
[`test_e2e_blueprint.py`](tests/test_e2e_blueprint.py).

## What It Produces

Every completed research round produces two first-class artifacts:

1. **Technical Research Package** for an implementation agent. It contains the
   repository baseline, Decision Ledger, recommended design, alternatives,
   implementation boundaries, validation plan, readiness result, and unresolved
   assumptions.
2. **Human Brief** for the requester. It explains what was understood, the
   recommended direction, the consequential trade-offs, the expected technical
   outcome, and the important uncertainty without forcing the reader through
   the full implementation package.

OpenSpec artifacts are optional. When the user explicitly asks for them, the
Technical Research Package is converted into an OpenSpec proposal, specs,
design, and task list. They are not a default research deliverable.

## Default Flow

```text
Context pack
  (idea, articles, drafts, repository, prior feedback)
        |
        v
Repository/material analysis + proportionate alignment research
        |
        v
Intent Understanding / Intent Model
        |
        v
Working Brief + Blueprint Target + Research Strategy
        |
        v
Adaptive large-scale research around open design decisions
        |
        v
Decision Ledger -> Technical Research Package + Human Brief
        |
        +-- explicit request --> OpenSpec artifacts --> implementation agent
```

The default is autonomous. The skill does not turn every ambiguity into a
question or require continuous conversation. It consults the user only when
the user asks to co-explore, or when a consequential and non-recoverable choice
cannot be responsibly inferred from the available context.

## Research Strategy, Not a Fixed Pipeline

The central product artifacts before deep research are an **Intent Model**, a
**Blueprint Target**, and a **Research Strategy**. The Intent Model determines
what outcome the agent is trying to serve and which alternative readings remain
viable; the target defines the consequential technical decisions that must
close before an implementation agent can start; the strategy decides how to
investigate them, why they matter, how deeply to investigate them, which facts
should come from the repository versus external sources, and what counts as
closure.

Research runs first broad coverage across independent high-impact decisions,
then deepens only where evidence can change the blueprint. Workers return
traceable Finding Packs, and the coordinator compiles a Decision Ledger rather
than concatenating research reports. Completion is based on decision closure and
implementation readiness, not source count, task count, or report length.

Lightweight web research is allowed before the strategy is fixed when it helps
the agent understand supplied material or have a useful conversation. Once a
strategy is selected, the agent performs the deep research without repeatedly
returning routine unknowns to the user. It records assumptions, alternatives,
and validation work instead.

## Feedback Starts a New Round

Feedback is not a request to patch the previous report. It becomes one input to
a new Working Brief and a new research round:

```text
previous context + user feedback
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

Earlier findings are candidate context, not inherited truth. The new strategy
may reuse, revalidate, downgrade, ignore, or overturn them, and may regroup or
split prior Context Bundles. Only constraints the user explicitly keeps as
non-negotiable are carried forward automatically. A user who rejects the
overall direction starts a new root Working Brief instead.

## Existing Repositories

When a repository is supplied, it is a first-class source of technical truth.
The agent first reconstructs the relevant behavior, architecture, entry points,
dependencies, tests, interfaces, deployment boundaries, and change surface.
It does not ask the user for facts that can be discovered from the codebase.
External research must then be tied back to actual integration points rather
than describing a greenfield architecture.

## Product Documents

- [Product specification](PRODUCT.md): target behavior, artifacts, state
  model, target algorithm/architecture, quality bar, and migration plan.
- [Skill instructions](SKILL.md): operational instructions for the research
  agent.
- [Product contracts](references/product-contracts.md): target state records
  for inputs, Context Bundles, Working Briefs, strategies, Blueprint Targets,
  decisions, and rounds.
- [Artifact templates](assets/): Working Brief, strategy, agent package, and human
  brief templates.
- [Blueprint generation research](references/blueprint-generation-research.md):
  evidence, algorithm, architecture, and evaluation design for the new loop.

## Retired Runtime

The previous mandatory intent gate, recursive evidence DAG, source-review
stages, snapshot freeze, and multi-chapter report pipeline have been removed.
They are available only in repository history. A future high-assurance research
adapter may reuse selected ideas, but it must be built as an explicit opt-in
component and must not restore the retired workflow as the default experience.
