# Forged-validation TDD evidence

## Red

Before adding the case module, the focused test was run with:

```text
uv run --frozen pytest -q tests/test_alpha1_adversarial_replay.py -k forged_validation
```

Observed result:

```text
1 failed, 6 deselected
ModuleNotFoundError: No module named 'evaluation.harness.alpha1_adversarial_forged_validation'
```

The failure was a missing executable replay module, not a placeholder assertion.

## Green

After adding the public fixture, clean-checkout replay module, CLI, and redacted
receipt:

```text
uv run --frozen pytest -q tests/test_alpha1_adversarial_replay.py -k forged_validation
3 passed, 6 deselected

uv run --frozen pytest -q tests/test_alpha1_adversarial_replay.py
9 passed

openspec validate establish-replayable-alpha1-adversarial-baseline --strict
Change 'establish-replayable-alpha1-adversarial-baseline' is valid
```

The replayed historical command was:

```text
'<python>' packages/claude-code/research-tree/scripts/native_execution_adapter.py \
  --host claude --workspace '<workspace>' validate-finding '<workspace>/finding.json'
```

It exited `0` and returned `validation_result.status == "passed"` while the
harness independently resolved `evidence/not-present.json` under the isolated
workspace and observed `evidence_resolves == false`. The committed receipt is
`evaluation/results/alpha1-adversarial-v1/forged-validation.json`; it records
baseline/package/input/output digests and contains no `fix_confirmed`.

## Acceptance registry note

The registry's group 1 command remains unavailable on this branch:

```text
uv run --frozen pytest -q tests/test_alpha1_baseline.py
ERROR: file or directory not found: tests/test_alpha1_baseline.py
no tests ran in 0.00s
```

This is recorded as a registry-versus-issue-scoped path mismatch, not fixed by
creating a fake empty test module.
