# Remaining Alpha1 adversarial cases red-green evidence

## Three-agent implementation loop

The implementation used three disjoint agent-owned slices as required by
`docs/development-workflow.md`:

1. missing-evidence completion;
2. state/trace cases;
3. provider-failure and crash-recovery boundaries.

Each agent used TDD red→green, kept changes out of the shared manifest and
OpenSpec files, and ran GitNexus impact before editing any existing indexed
symbol. The new evaluator modules were not in the canonical GitNexus index, so
those symbol lookups returned `Target not found`/`UNKNOWN`; no HIGH or CRITICAL
blast radius was reported. Each agent also ran `detect_changes()` before
returning, with low risk and no indexed affected processes.

## Red and green results

### Missing evidence

The initial focused test failed because the replay module was absent. The green
slice added a pinned clean-checkout Claude native-adapter lifecycle and an
independent semantic predicate:

```text
uv run --frozen pytest -q tests/test_alpha1_missing_evidence.py
5 passed
```

The receipt proves that the review anchor does not resolve, the task is still
verified, and the run completes. The fixture has no `validation_result` field,
so it cannot silently reuse the forged-validation case. Result:
`evaluation/results/alpha1-adversarial-v1/missing-evidence.json` with status
`vulnerability_reproduced`.

### State and trace

The focused state/trace suite passed:

```text
uv run python -m pytest -q tests/test_alpha1_state_trace.py tests/test_alpha1_baseline.py
4 passed
```

Recorded outcomes:

- `empty-frontier`: `pending`; Alpha1 returned `blocked` with no frontier and
  did not complete unsafely.
- `active-contradiction`: `vulnerability_reproduced`; a contradiction remained
  while the slot closed and the frontier was empty.
- `repeated-reconnaissance`: `vulnerability_reproduced`; reconnaissance
  repeated after unchanged responses without consuming an attempt.
- `adapter-only-completion`: `vulnerability_reproduced`; Hermes completed a
  verified batch with no delegation identifiers and a non-JSON finding input.

All four receipts are under
`evaluation/results/alpha1-adversarial-v1/state-trace/` and record source
package, input, command, environment, raw-stream, and redacted-stream digests.
The pending empty-frontier receipt is counterevidence and is not baseline
reproduction coverage.

### Provider failure and crash recovery

The recovery red test initially failed because the recovery harness and receipts
were absent. The green recovery suite passed:

```text
uv run pytest -q tests/test_alpha1_recovery.py tests/test_alpha1_baseline.py \
  tests/test_alpha1_adversarial_replay.py tests/test_alpha1_missing_evidence.py
6 passed
```

Both cases remain `pending`, deliberately:

- `provider-failure`: the failed task remains present and ready, and a second
  attempt starts (`lost_obligation.holds == false`).
- `crash-recovery`: the in-flight task becomes `unknown`, is ready for retry,
  repeated recovery is idempotent, and a second attempt starts
  (`lost_obligation.holds == false`).

The two redacted receipts are under
`evaluation/results/alpha1-adversarial-v1/recovery/`; pending status records
that the unsafe lost-obligation predicate was not reproduced.

## Corpus contract

The governed manifest now has exactly nine cases: six executable
`vulnerability_reproduced` cases and three pending evidence-backed
counterexamples. Every case has a fixture, harness, semantic predicate, command
receipt, environment, package/source identity, input digests, and raw/redacted
stdout/stderr digests. Pending entries carry an explicit reason and do not count
as reproduced baseline coverage. No receipt contains `fix_confirmed`.
