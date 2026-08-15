# Evaluation Asset Schemas

`public-case-v1.schema.json` describes the worker-visible case envelope. The
existing `evaluation/cases/v1.json` and Alpha1 adversarial manifest remain
compatibility fixtures and are validated by the governance checker.

`retained-evidence-v1.schema.json` is the provenance minimum for baselines,
redacted results, and blinded reviews. Hidden oracle bodies, reference patches,
credentials, private prompts, and provider transcripts are evaluator-owned and
must never be stored in these public assets.

`claude-glm-regression-v1.schema.json` defines the Issue #72 public fixture.
It permits only synthetic, non-historical turns and an opaque oracle identifier;
it cannot establish a historical replay or GLM causal attribution.
