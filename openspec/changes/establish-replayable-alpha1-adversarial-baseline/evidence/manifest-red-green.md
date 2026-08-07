# Alpha1 adversarial manifest red-green evidence

## Red

The task-execution registry's group-1 acceptance command was missing its
registered test path:

```text
uv run --frozen pytest -q tests/test_alpha1_baseline.py
ERROR: file or directory not found: tests/test_alpha1_baseline.py
exit 4
```

The new manifest contract test initially failed because the governed corpus
manifest did not exist:

```text
uv run --frozen pytest -q tests/test_alpha1_baseline.py
FileNotFoundError: evaluation/baselines/alpha1-adversarial-v1.json
exit 1
```

## Green

After adding the versioned nine-defect manifest and contract test:

```text
uv run --frozen pytest -q tests/test_alpha1_baseline.py
1 passed
```

The manifest contains exactly nine issue #55 defect IDs. Six entries are
executable (`filler-report`, `forged-validation`, `missing-evidence`,
`active-contradiction`, `repeated-reconnaissance`, and
`adapter-only-completion`) and three remain explicitly `pending`
(`empty-frontier`, `provider-failure`, and `crash-recovery`). Pending entries
now carry evidence receipts that record why the unsafe predicate was not
reproduced; they do not count as reproduction coverage. Every executable receipt
is `vulnerability_reproduced`, never `fix_confirmed`.

This closes tasks 3.1b, 3.2, 3.3, and 3.4 in addition to the governed-manifest
follow-up 3.4a. It does not claim the three pending unsafe predicates were
reproduced.

## Legacy receipt digest follow-up

The filler receipt now carries both the original command-stream digest and the
digest of the path-redacted stream:

```text
raw_stdout_sha256 == stdout_sha256
redacted_stdout_sha256 !=/or independently verifies the stored redacted stdout
raw_stderr_sha256 == stderr_sha256
redacted_stderr_sha256 !=/or independently verifies the stored redacted stderr
```

The recorded receipt and focused regression assert these fields. This closes
follow-up 3.4b; cleanup/help reconciliation is covered by the caller-owned-root help test and
is closed as follow-up 3.4c.
