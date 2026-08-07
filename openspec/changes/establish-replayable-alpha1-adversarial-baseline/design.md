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
input/output digests, baseline/package identity, and limitations. For the forged
validation slice, the semantic predicate independently resolves the declared
`evidence_ref` below the isolated workspace and requires that it is absent while
the pinned native adapter still returns a parsed `passed` result. The opaque
`oracle` and `evidence_ref` strings are therefore not treated as proof. Future
Alpha2 fix confirmation must be a different candidate-run evaluation with a
resolvable, case-bound evidence receipt. This baseline harness never returns
`fix_confirmed`.

## Data boundaries

- `evaluation/baselines/` stores immutable identity and replay environment data.
- `evaluation/fixtures/` stores public, versioned, non-secret inputs.
- `evaluation/harness/` holds evaluator-only runner code and is excluded from
  host-package generation.
- `evaluation/results/` will hold redacted append-only committed results;
  temporary raw streams remain only below a disposable caller-specified work dir.

## Incremental plan

The corpus now has independent executable receipts for filler-report,
forged-validation, missing-evidence, active-contradiction,
repeated-reconnaissance, and adapter-only completion. Empty-frontier executes
against the pinned Alpha1 research state but remains pending because Alpha1
blocked rather than completing unsafely. Provider-failure and crash-recovery
also remain pending because their explicit lost/recovered-obligation predicates
show that Alpha1 preserves a retryable obligation. These pending receipts are
counterevidence and do not count as reproduced defects; they remain governed so
all nine issue identifiers have replayable evidence rather than speculative
claims.

## Operator replay contract

The replay cases are exposed as evaluator-only module CLIs. The existing
filler command is:

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

The forged-validation slice is replayed independently with:

```bash
uv run --frozen python -m evaluation.harness.alpha1_adversarial_forged_validation \
  --repository-root . \
  --work-root /tmp/research-tree-alpha1-forged-validation \
  --receipt /tmp/research-tree-alpha1-forged-validation-receipt.json
```

Its redacted receipt records the pinned Claude package digest, finding input
digest, Python/platform environment, command and stdout/stderr digests, and the
independently observed `evidence_resolves: false` predicate.

## Registry acceptance boundary

The root Alpha2 task registry names group 1's acceptance command as
`uv run pytest -q tests/test_alpha1_baseline.py`. This issue-scoped branch now
provides that real contract test; it validates the governed nine-defect manifest
and does not use an empty alias or count pending cases as green.

The governed `evaluation/baselines/alpha1-adversarial-v1.json` manifest provides
the registered group-1 contract test with all nine defect IDs, explicitly
separating executable receipts from pending cases. Legacy filler receipts now
retain raw stdout/stderr digests and add distinct redacted stdout/stderr digests,
so a redacted stream is not misrepresented as proof of the raw digest.

## Expanded replay commands

The remaining evaluator-only CLIs are:

```bash
uv run --frozen python -m evaluation.harness.alpha1_adversarial_missing_evidence \
  --repository-root . --work-root /tmp/alpha1-missing-evidence \
  --receipt /tmp/alpha1-missing-evidence.json
uv run --frozen python -m evaluation.harness.alpha1_adversarial_state_trace \
  --repository-root . --work-root /tmp/alpha1-state-trace \
  --results-dir /tmp/alpha1-state-trace-results
uv run --frozen python -m evaluation.harness.alpha1_adversarial_recovery \
  --case provider-failure --repository-root . \
  --work-root /tmp/alpha1-provider-failure \
  --receipt /tmp/alpha1-provider-failure.json
uv run --frozen python -m evaluation.harness.alpha1_adversarial_recovery \
  --case crash-recovery --repository-root . \
  --work-root /tmp/alpha1-crash-recovery \
  --receipt /tmp/alpha1-crash-recovery.json
```

The caller owns each `work_root`. Default cleanup removes the generated detached
checkout and runtime workspace, leaving the reusable root directory empty.
