## Context

The repository already ignores runtime state under `.research-tree/`, but older
verification tooling writes command output and JSON receipts below tracked
`openspec/changes/**/evidence/` paths. `.gitignore` cannot untrack those
existing files and cannot stop a force-add, so prevention and historical
migration must be separate deliveries.

## Decisions

1. Local verification records use `.research-tree/verification-runs/`, which
   is an existing ignored runtime boundary.
2. Ignore rules are narrow: they match known generated file forms and tooling
   directories, never generic `*.json`, `*.txt`, `evidence/`, or
   `evaluation/` roots.
3. Pull-request validation rejects only *newly added* generated verification
   paths. Historical tracked records remain available until a reference-safe
   migration changes the registries that name them.
4. Receipt-generation APIs reject destinations below
   `openspec/changes/**/evidence/` and require the ignored verification-run
   boundary instead.

## Retained Source Classes

- OpenSpec proposals, designs, tasks, and capability specifications.
- Versioned schemas, semantic fixtures, redacted evaluation results, and
  human-authored review artifacts.
- Source code, package inputs, and release-manifest definitions.

## Follow-up Migration

The audit found 86 currently tracked generated output/receipt candidates. They
must be removed in bounded registry migrations after this prevention gate is
merged. Each migration replaces raw-output references with CI-check policy
metadata and deletes only the files whose references it updates.
