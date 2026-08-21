# Agent Guide

This guide is for any AI agent using, integrating, reviewing, or continuing a
Research Tree run. Codex, Claude Code, and Hermes Agent are current hosts; the
research method is not limited to coding agents or implementation work.

## What The Skill Adds

Research Tree gives an agent a governed research loop:

~~~text
uncertain request
  -> shared working understanding
  -> explicit decision gaps
  -> bounded research tracks
  -> traceable evidence and findings
  -> reviewed decision state
  -> Human Research Report + Technical Research Package
~~~

The agent may investigate technical, product, operational, security, vendor,
governance, or migration questions. Code changes are only one possible
downstream action.

## Minimum Context By Task

| Agent task | Load first | Load only if needed |
| --- | --- | --- |
| Use the installed Skill | The host package entry point | Bundled references named by that entry point |
| Explain the product | This guide and [README](../README.md) | Relevant sections of [PRODUCT.md](../PRODUCT.md) |
| Continue a research run | Durable run status, latest working brief, active decision map | Prior findings that remain reachable from the current revision |
| Plan an implementation | Technical Research Package | Selected ADRs, active OpenSpec change, repository code and tests |
| Review product behavior | [PRODUCT.md](../PRODUCT.md) | Current source, tests, receipts, and selected ADRs |
| Modify the Skill | [Development workflow](development-workflow.md) | Canonical source under <code>skill-src/</code>, <code>assets/</code>, <code>references/</code>, <code>scripts/</code>, or <code>src/</code> |

Do not load all historical specifications, all OpenSpec changes, or all
generated packages. More context is not automatically better context.

## Authority Rules

Use [documentation authority](documentation-authority.md) when two sources
conflict.

- <code>PRODUCT.md</code> defines accepted product behavior.
- ADRs define accepted architecture decisions.
- A selected active OpenSpec change defines pending implementation scope.
- <code>skill-src/</code>, <code>assets/</code>,
  <code>references/</code>, registered scripts, and <code>src/</code> are
  canonical authoring sources.
- <code>packages/</code> and <code>.claude-plugin/</code> are generated
  distributions.
- <code>docs/specs/</code>, <code>docs/reviews/</code>, and the two legacy
  consolidated notes are historical records.
- Evaluation reports describe evidence under their stated conditions; they do
  not silently redefine the product.

When a runtime claim matters, confirm it in current code, tests, or a reachable
receipt. A README sentence is not runtime proof.

## Starting A Research Interaction

Accept incomplete input. A useful opening can be one sentence plus any
available files, links, logs, screenshots, or constraints.

Determine together:

1. the decision or outcome the requester actually needs;
2. what is in and out of scope;
3. which actions the agent is authorized to take;
4. who owns consequential decisions;
5. what evidence would make the result usable;
6. what is already known, attempted, disputed, or time-sensitive.

Do not force the requester through a fixed questionnaire. Ask the smallest
question that can materially change the model or research strategy.

## Building Shared Knowledge

Maintain a living model rather than a transcript summary:

| Knowledge object | Purpose |
| --- | --- |
| Working understanding | Current outcome, scope, authority, constraints, terms, and unresolved disagreements. |
| Decision map | Questions that must be closed, conditioned, deferred, or explicitly rejected. |
| Research strategy | Bounded tracks selected for decision value, not topic coverage. |
| Evidence ledger | Sources, observations, experiments, provenance, currentness, confidence, and limitations. |
| Finding packs | Atomic findings tied to decision gaps, including counterevidence and uncertainty. |
| Decision ledger | Selected, conditional, deferred, and rejected options with rationale and consequences. |

User corrections supersede stale assumptions. New contradictions can reopen a
decision. Historical attempts remain visible without being mistaken for the
current state.

## Research And Tool Use

- Use repository inspection, web sources, documents, experiments, or host
  workers only when they can change a decision.
- Keep source evidence, test evidence, prototype evidence, and real-world
  feasibility distinct.
- Bind worker output to a concrete attempt and preserve unknown outcomes when
  the host cannot prove completion.
- Parallelize independent decision gaps; serialize only actual dependencies.
- Stop repeating a source or experiment once it no longer reduces material
  uncertainty.

Host access is capability, not authority. A tool succeeding does not grant
permission for purchasing, deployment, policy change, implementation, or
external communication.

## Producing The Deliverables

The **Human Research Report** should let a decision owner understand:

- the recommendation and why it matters;
- what evidence changed the direction;
- important alternatives and trade-offs;
- what is known, uncertain, conditional, or blocked;
- which decision or approval remains with a human.

The **Technical Research Package** should let another agent continue:

- the current working understanding and decision map;
- evidence-backed findings with provenance and limits;
- selected and rejected alternatives;
- affected systems, interfaces, people, or processes;
- implementation or operating steps when requested;
- validation, rollout, rollback, and stop conditions;
- unresolved risks and the exact next evidence needed.

Both outputs must describe the same decision state. OpenSpec is an optional
conversion for implementation work and is created only when requested.

## Completion And Handoff

Do not claim completion because:

- a worker stopped or returned prose;
- a command exited zero;
- a report was generated;
- a visible task list says done;
- the evidence is persuasive but not reachable from the current run.

Completion requires the agreed outcome and success signal, closed or explicitly
conditioned high-impact decisions, current authority, and both delivery views.
If the requester corrects a consequential assumption, revise the knowledge
state and any dependent handoff before continuing.

## Stable Lifecycle Commands

Run repository tooling through the <code>uv</code>-managed environment.

~~~bash
uv run --frozen research-tree doctor --host all --source /path/to/research-tree
uv run --frozen research-tree status \
  --workspace /path/to/workspace --host codex \
  --project-id example --run-id example-001
uv run --frozen research-tree resume \
  --workspace /path/to/workspace --host codex \
  --project-id example --run-id example-001
uv run --frozen research-tree verify \
  --workspace /path/to/workspace --host codex \
  --project-id example --run-id example-001
~~~

Use the [operator guide](operator-guide.md) for installation and host-specific
diagnostics. Use [typical research journeys](use-cases.md) for complete
examples.
