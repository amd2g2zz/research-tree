# Generated Artifact Audit

## Inventory

The `origin/dev` baseline contains 86 tracked generated verification records:

| Class | Count | Examples | Disposition |
| --- | ---: | --- | --- |
| Group stdout/receipt pairs | 66 | `group-*-output.txt`, `group-*-receipt.json` | Migrate by registry slice |
| Human-readable verification summaries | 7 | `verification-YYYY-MM-DD.md` | Migrate by registry slice |
| Integrated run bundle | 13 | `integrated-*-output.txt`, `future-evidence-gaps.json`, `integrated-strict-slices.json` | Migrate as one bounded slice |

The files are not ignored retroactively because the shared task-verification
registry and direct tests still name them. Removing them without changing
those consumers would turn a source-control cleanup into a false verification
claim.

## Retained classes

The following remain source-controlled:

- OpenSpec proposals, designs, tasks, capability specs, and schemas.
- Semantic fixtures such as `policy-fixtures.json`, intent fixtures, lineage
  models, and redacted evaluation source assets.
- Release manifests and human-authored review notes.

No generic `evidence/`, `*.json`, `*.txt`, `evaluation/`, `*.tmp`, or `*.bak`
rule is used because each would hide normative or operator-review material.
`.vscode/` is also intentionally retained as a possible team configuration
surface; only `.vscode-test/` is local-only.

## Prevention boundary

New records are blocked in two independent ways:

1. `.gitignore` covers the local `.research-tree/verification-runs/` boundary,
   known output/receipt names, reporting directories, type-checker caches,
   profiler output, GitNexus state, private IDE state, and editor recovery
   files.
2. The delivery gate examines Git additions (not all modifications) and
   rejects force-added generated verification records using the same policy
   patterns. Historical migrations can therefore delete or update existing
   records without being blocked by the new guard.

## Migration order

The shared verification registry requires serial pull requests. Each follow-up
is kept at or below the 25-file split-review threshold:

- #189: groups 1–9 (22 generated files).
- #190: groups 10–21, seven historical Markdown summaries, and the worktree
  inventory (24 generated files).
- #191: groups 23–32 (14 generated files).
- #192: groups 33–35 and the integrated bundle (15 generated files).
- #193: groups 42 and 46 (4 generated files).
- #194: groups 54–60 (10 generated files).

Each migration replaces raw-output references with CI-check metadata before
deleting only the exact files it owns.
