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

## Paired Research Benchmark

`evaluation/benchmarks/paired-research-v1.json` is a public protocol commitment,
not a task corpus or a result. Its six cells are evaluated separately: baseline,
Alpha1, and Alpha2 under each of Claude Code and Hermes Agent, all using the
same frozen DeepSeek V4 Flash revision. The benchmark never pools host scores.

The primary live-research panel, reliability repeats, fixed integrity tasks,
actual task text, user-persona system prompts, scorer rubric, source captures,
and raw transcripts are evaluator-owned. They belong only in an ignored
`.research-tree/evaluation-runs/` directory or an external evaluator store. A
fresh checkout therefore reports the paired runner as `unavailable`; that is an
honest state, not a passing benchmark result.

Synthetic user simulation is labeled `synthetic-user-proxy` and always reports
human-experience evidence as `unavailable`. It is a behavior stressor, not a
substitute for a user study. Persona prompts are task-agnostic, the task set is
held out from harness development, and prompt/assignment commitments are kept
only as evaluator-owned digests until unblinding. The tested runner sees only a
user turn and controlled source/model proxy endpoints. It does not receive a
host or condition label, hidden prompt, expected answer, reference patch, or
scoring outcome. Every paired task-repeat commits identical runner input and
synthetic-user assignment digests across all six cells.

The simulator never receives a task context, reference answer, rubric, host,
arm, condition, or score. It accepts one strictly sequential turn stream for
each opaque conversation, so a runner cannot re-sample a simulated user to
choose a favorable response. A separate reviewer receives only a blinded
transcript and must record a `blinded-independent-review-v1` provenance record;
the synthetic user cannot generate or influence the quality score.

## Retention And Migration

Baselines are immutable by digest. Results and reviews are append-only,
provenance-complete, redacted summaries retained for the release audit period.
Raw runs use `.research-tree/evaluation-runs/` and operator-defined retention.

Local `evaluation/experiences/` content is user-owned legacy input. Governance
reports the directory as a migration candidate by path only. It never reads,
moves, deletes, truncates, or stages those files. A maintainer must manually
classify, redact, and validate any item before retaining it in a tracked class.
