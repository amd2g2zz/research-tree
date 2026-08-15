# Evaluation Entry Points

The governed public entry point is:

```text
uv run python scripts/check_evaluation_assets.py --public-alpha1
```

It validates the path registry and the public Alpha1 manifest without running
hidden oracles or writing output under tracked evaluation paths. Unit,
integration, black-box, cross-host, and expert-review command identities are
registered in `evaluation-paths-v1.json`; unavailable private components must be
reported as unavailable rather than inferred as passing.

The Issue #72 fixture is explicitly synthetic and non-historical:

```text
uv run python evaluation/harness/run_claude_glm_regression.py --expect-status unavailable
```

It evaluates deterministic control transitions but does not execute a live
Claude Code or GLM runtime. A missing GLM runtime produces a named
`unavailable` result and cannot establish parity or causal attribution.

The Issue #84 protocol gate is likewise intentionally unavailable in a clean
checkout:

```text
uv run python evaluation/harness/run_paired_benchmark.py --expect-status unavailable
```

It validates the executable boundary for a sealed paired benchmark. A real run
supplies an evaluator-owned manifest and records from outside tracked
`evaluation/`; the result is a host-specific synthetic-user proxy analysis, not
human-preference evidence. The sealed manifest binds each paired task-repeat to
one shared runner-input digest and one shared synthetic-user assignment digest.
Its prompt bank is task-agnostic and held out from harness development; a
separate arm-and-host-blinded review records quality, never the synthetic user.
