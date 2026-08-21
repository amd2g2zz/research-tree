# Documentation Hub

Research Tree is used by requesters, operators, contributors, and AI agents.
This directory makes the active reading path visible before anyone loads more
context than the task needs.

```text
docs/
├── guides/        requester, agent, operator, and worked-journey guidance
├── contributing/  delivery workflow for maintainers and reviewers
├── governance/    documentation and evaluation authority
├── architecture/  index for the accepted ADR collection
├── evaluation/    active evaluation material and research records
├── history/       router for preserved historical evidence
├── adr/           accepted architecture decisions at stable paths
├── specs/          historical specifications at stable paths
└── reviews/        historical review records at stable paths
```

## Choose Your Path

| Reader | Start here | Then load only when needed |
| --- | --- | --- |
| Requester or decision owner | [Project overview](../README.md) | [Typical research journeys](guides/use-cases.md) |
| AI agent using the Skill | [Agent guide](guides/agent.md) | Relevant [product specification](../PRODUCT.md) section and selected authority |
| Host operator or integrator | [Operator guide](guides/operator.md) | [Contributor workflow](contributing/development-workflow.md) for source changes |
| Contributor or reviewer | [Contributor documentation](contributing/README.md) | [Architecture index](architecture/README.md) and selected active OpenSpec change |
| Evaluator or auditor | [Evaluation documentation](evaluation/README.md) | [History router](history/README.md) for revision-bound records |

## Current Guidance

- [Guides](guides/README.md) — product use, agent operating model, host setup,
  and representative research journeys.
- [Contributing](contributing/README.md) — issue, branch, worktree, pull
  request, package-generation, and release workflow.
- [Governance](governance/README.md) — documentation precedence and evaluation
  asset rules.
- [Architecture](architecture/README.md) — accepted ADRs and their relation to
  current product behavior.
- [Evaluation](evaluation/README.md) — active evaluation material and its
  boundary from raw or sealed run data.

## Historical Evidence

[History](history/README.md) separates old specifications, review records, and
consolidated early notes from current guidance. These records remain at stable
paths because active and historical OpenSpec material may cite them. They are
not product, architecture, or implementation authority for new work.

## Authority At A Glance

When sources disagree, use this order:

1. [Product specification](../PRODUCT.md) for accepted product behavior.
2. [Architecture decisions](adr/) for accepted architecture.
3. The relevant active [OpenSpec change](../openspec/changes/) for pending
   implementation scope.
4. Normative references, templates, and Skill authoring sources.
5. Current guides and operational procedures.
6. Evaluation evidence and historical records under their stated conditions.

The machine-readable authority inventory is
[`documentation-authority-v1.json`](../openspec/changes/unify-research-runtime-alpha2/registries/documentation-authority-v1.json).

## Minimal Agent Reading Path

Do not recursively ingest `docs/`, `openspec/changes/`, or `packages/`.

1. Load the [Agent guide](guides/agent.md).
2. Load the task-relevant section of [PRODUCT.md](../PRODUCT.md).
3. Load one selected ADR or one active OpenSpec change only if it governs the
   task.
4. Validate runtime claims against executable code, tests, and reachable
   receipts; generated packages and history are revision-bound evidence.

## Editing Rules

- Edit active guides, governance material, and indexes in their canonical
  directories; update the authority registry whenever a canonical location
  changes.
- Edit `skill-src/`, `assets/`, `references/`, or registered scripts for
  packaged Skill content, never generated `packages/` copies.
- Preserve history unless correcting a factual error in that historical record.

~~~bash
uv run --frozen python scripts/check_docs.py
uv run --frozen python scripts/build_skill_packages.py --check
~~~
