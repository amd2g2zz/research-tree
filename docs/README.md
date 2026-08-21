# Documentation Hub

Research Tree documentation serves several readers with different questions.
Use this page as the router; do not read every directory as though every file
were current product guidance.

## Start By Role

| Reader | First document | Next document |
| --- | --- | --- |
| Requester or decision owner | [Project overview](../README.md) | [Typical research journeys](use-cases.md) |
| AI agent using the Skill | [Agent guide](agent-guide.md) | [Product specification](../PRODUCT.md) only when deeper behavior is needed |
| Host operator or integrator | [Operator guide](operator-guide.md) | [Development workflow](development-workflow.md) |
| Contributor or reviewer | [Product specification](../PRODUCT.md) | [Architecture decisions](adr/) and the relevant active OpenSpec change |
| Evaluator or auditor | [Evaluation asset governance](evaluation-assets.md) | [Research and evaluation records](research/) |

## Documentation Map

### Active product and usage

- [README](../README.md) — product purpose, representative cases, quick start,
  supported hosts, and evidence boundary.
- [Typical research journeys](use-cases.md) — complete examples showing how
  uncertain inputs become structured knowledge and decisions.
- [Agent guide](agent-guide.md) — minimal context loading, authoritative
  sources, operating expectations, and handoff rules for AI agents.
- [Operator guide](operator-guide.md) — installation, host configuration,
  lifecycle CLI, diagnostics, hooks, and debug tracing.
- [Product specification](../PRODUCT.md) — current product behavior and
  normative research model.

### Architecture and delivery

- [Architecture decisions](adr/) — accepted, durable architecture decisions.
- [Development workflow](development-workflow.md) — issue, branch, worktree,
  pull request, generated package, and release rules.
- [Documentation authority](documentation-authority.md) — precedence,
  lifecycle, ownership, and canonical edit locations.
- Active [OpenSpec changes](../openspec/changes/) — pending implementation
  contracts and their evidence.

### Evaluation and audit material

- [Evaluation asset governance](evaluation-assets.md) — what belongs in the
  evaluation namespace and how evidence is retained.
- [Research records](research/) — issue-scoped research and evaluation design.
- [Historical specifications](specs/) — preserved product history; they do not
  override the current product specification.
- [Historical reviews](reviews/) — audit records tied to a past revision or
  acceptance event.

### Legacy consolidated notes

- [Legacy requirements notes](需求理解.md)
- [Legacy design notes](方案设计.md)

These two files are preserved for traceability. They combine several early
delivery rounds and are not entry points for current behavior. Prefer
[PRODUCT.md](../PRODUCT.md), [ADRs](adr/), and active OpenSpec changes.

## Authority At A Glance

When sources disagree, use this order:

1. [Product specification](../PRODUCT.md) for accepted product behavior.
2. [Architecture decisions](adr/) for accepted architecture.
3. The relevant active OpenSpec change for pending implementation scope.
4. Normative references, templates, and Skill authoring sources.
5. User, Agent, operator, and contributor guides.
6. Operational records, historical specs, reviews, generated packages, and
   evaluation evidence.

The machine-readable authority inventory is
[documentation-authority-v1.json](../openspec/changes/unify-research-runtime-alpha2/registries/documentation-authority-v1.json).

## For Agents: Load Less, Know More

Do not recursively ingest <code>docs/</code>, <code>openspec/changes/</code>,
or <code>packages/</code>.

1. Load [Agent guide](agent-guide.md).
2. Load the [product specification](../PRODUCT.md) section relevant to the
   task.
3. Load only the selected ADR or active OpenSpec change.
4. Treat generated packages and historical records as evidence about a
   revision, not as current authority.
5. Verify claims against executable code, tests, and receipts when the task
   depends on runtime behavior.

## Editing Rules

- Edit <code>README.md</code> and <code>docs/</code> for active guides.
- Edit <code>skill-src/</code>, <code>assets/</code>,
  <code>references/</code>, or registered scripts for packaged Skill content.
- Never edit <code>packages/</code> as an authoring source.
- Preserve historical records unless correcting a factual error in that
  record.
- Update the authority registry when adding a new governed documentation root
  or changing its audience, lifecycle, or precedence.

~~~bash
uv run --frozen python scripts/check_docs.py
uv run --frozen python scripts/build_skill_packages.py --check
~~~
