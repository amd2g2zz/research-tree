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
