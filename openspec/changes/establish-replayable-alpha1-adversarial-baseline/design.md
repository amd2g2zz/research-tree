## Evidence and root cause

Three independent roles assessed the former #55 candidate:

- The operations persona confirmed Alpha1 tag `0.0.1-a1` can run its ordinary
  regression suite, but its adversarial manifest contains nine `unavailable`
  cases and a caller-injected classifier rather than host replays.
- The evaluation/audit persona confirmed a clean checkout can validate fixture
  shape but cannot execute any case, has no inputs/commands/raw receipts, and
  cannot treat a non-empty string as semantic fix evidence.
- The root-cause/TDD owner confirmed Alpha1's Hermes adapter accepts reports
  solely by byte and heading thresholds. Its own historical tests create padding
  reports and complete successfully, making filler-report an immediate semantic
  replay candidate.

## Replay model

The evaluator harness receives a repository root and creates a temporary detached
Git worktree at commit `8ab91ea4eb55c98441b5ee6001b80922a56ecdd1`. It verifies the
materialized HEAD, executes only a script in the recorded host-package path, and
removes the temporary worktree afterwards. The production checkout is never used
as the baseline runtime.

A case result is `vulnerability_reproduced` only when its semantic predicate
observes an unsafe Alpha1 result. For filler-report the predicate is specifically:

1. fixture reports contain only required Markdown headings plus repeated padding;
2. their byte/heading sizes satisfy the legacy structural threshold; and
3. the pinned Hermes adapter returns exit 0 with `status == "complete"`.

A command exit 0 alone is insufficient; the result retains parsed status,
input/output digests, baseline/package identity, and limitations. Future Alpha2
fix confirmation must be a different candidate-run evaluation with a resolvable,
case-bound evidence receipt. This baseline harness never returns `fix_confirmed`.

## Data boundaries

- `evaluation/baselines/` stores immutable identity and replay environment data.
- `evaluation/fixtures/` stores public, versioned, non-secret inputs.
- `evaluation/harness/` holds evaluator-only runner code and is excluded from
  host-package generation.
- `evaluation/results/` will hold redacted append-only committed results;
  temporary raw streams remain only below a disposable caller-specified work dir.

## Incremental plan

The first TDD slice intentionally covers only filler-report. The eight remaining
issue-named defects are catalogued as pending; no unavailable catalogue entry is
claimed as a reproduction. Subsequent slices must introduce exact state/trace
predicates for forged validation, missing evidence, empty frontier, active
contradiction, repeated reconnaissance, adapter-only completion, provider
failure, and crash recovery.

## Operator replay contract

The filler replay is also exposed as an evaluator-only module CLI:

```bash
uv run --frozen python -m evaluation.harness.alpha1_adversarial \
  --repository-root . \
  --work-root /tmp/research-tree-alpha1-replay \
  --receipt /tmp/research-tree-alpha1-filler-receipt.json
```

The default execution root is disposable: both the detached Alpha1 checkout and
its generated runtime workspace are removed on success and failure. An operator
may pass `--keep-workspace` for forensic inspection; that is an explicit
non-default retention choice and requires a fresh work root for the next replay.
The receipt is written outside the execution root, contains redacted command and
stdout evidence, and uses a non-zero JSON error response for operational input or
replay failures.
