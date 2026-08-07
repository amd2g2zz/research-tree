## Why

Issue #55 requires a deterministic, executable Alpha1 adversarial baseline.
A pre-existing remote #55 candidate pins tag `0.0.1-a1` but marks all nine cases
unavailable and only classifies a caller-supplied boolean. Independent black-box
and root-cause review show that it does not replay Alpha1 behavior, capture a
command/environment/output receipt, or prove the stated semantic failures.

This change replaces that catalogue-only approach with a clean-checkout replay
harness. The first green slice reproduces Alpha1's filler-report completion
failure on the real Hermes package. Remaining known defects remain explicitly
pending until each has a deterministic fixture and semantic predicate.

## What Changes

- Pin the Alpha1 tag's peeled commit and actual host package paths/digests in a
  versioned baseline record.
- Add evaluator-only harness code outside the runtime and host packages. It
  materializes a temporary clean checkout of the pinned commit, executes a
  declared case, and emits a redacted receipt with command, environment,
  input/output digests, package digest, status, and limitations.
- Add versioned public fixture inputs. The first case proves a headings-plus-
  padding technical/human report reaches `complete` in Alpha1's Hermes adapter.
- Establish an explicit case inventory for the nine named issue defects. A case
  is not marked complete merely because it is catalogued; it needs an executable
  semantic reproduction.

## Non-goals

- Claiming the Alpha2 fix is confirmed.
- Calling a structurally complete report a quality report.
- Running external providers or packaging evaluator-only oracle code into any
  Codex, Claude Code, or Hermes host package.
- Inventing a tenth defect: issue #55 names nine specific failures, and an
  additional case requires independent confirmation before it enters the corpus.

## Impact

- New governed evaluation baseline, fixture, harness, results, OpenSpec contract,
  and regression tests.
- No production research runtime behavior changes.
