# Evaluation Asset Governance

`evaluation/` is the only versioned source namespace for evaluation assets.
Its registered classes are cases, schemas, harnesses, fixtures, baselines,
redacted results, and blinded reviews. `.research-tree/evaluation-runs/` is the
ignored disposable output root. `evals/` is retired and must not contain
tracked files.

The authoritative path, mutability, retention, byte-limit, schema, and command
contract is `evaluation-paths-v1.json`. Public case IDs and opaque oracle IDs
may be tracked. Oracle bodies, reference patches, private prompts, credentials,
and raw provider transcripts must remain evaluator-owned outside worker-visible
assets.

Run the clean-checkout public validation with:

```text
uv run python scripts/check_evaluation_assets.py --public-alpha1
```

The command is read-only and deterministic. It validates the public Alpha1
manifest and governed paths; it does not execute unavailable hidden components
or write generated output into `evaluation/`.

## Research Evaluation Design

Issue #268's design and handoff reports are maintained under
[`docs/evaluation/research/`](../evaluation/research/issue-268-comprehensive-evaluation-design.md):

- [comprehensive evaluation design](../evaluation/research/issue-268-comprehensive-evaluation-design.md)
- [Technical Research Package](../evaluation/research/issue-268-technical-research-package.md)
- [Human Research Report](../evaluation/research/issue-268-human-research-report.md)

These documents define the baseline, task clusters, hidden holdouts, paired
statistics, hard integrity gates, and execution boundary. They are design
artifacts; they do not claim that the sealed benchmark has run.

## Retention And Migration

Baselines are immutable by digest. Results and reviews are append-only,
provenance-complete, redacted summaries retained for the release audit period.
Raw runs use `.research-tree/evaluation-runs/` and operator-defined retention.

Local `evaluation/experiences/` content is user-owned legacy input. Governance
reports the directory as a migration candidate by path only. It never reads,
moves, deletes, truncates, or stages those files. A maintainer must manually
classify, redact, and validate any item before retaining it in a tracked class.
