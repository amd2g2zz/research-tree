# Human Research Report: issue-268-evaluation

This active evaluation report is indexed from [evaluation documentation](../README.md).

## What We Now Understand

The project does not need one larger score. It needs a controlled comparison
that answers three separate questions:

1. Does Alpha2 improve over Alpha1 on evidence-backed research behavior?
2. How much of that result is attributable to Research Tree rather than the
   native host, model, or provider?
3. Does the result survive correction, interruption, recovery, human review,
   and independent implementation?

The correct baseline is the native Claude Code, Hermes, and Codex host without
Research Tree installed or activated. A simplified Research Tree prompt is an
ablation, not the baseline.

## Direction

Use three arms per host: native baseline `B`, pinned Alpha1 `A1`, and pinned
Alpha2 `A2`. Keep the target nine-cell matrix, but allow a cell to be explicitly
`unavailable` rather than substituting another host.

Use 24 task clusters across four families, with five evaluator-owned hidden
holdouts. Put long interaction and fault injection inside the same clusters so
the evaluation remains affordable. Start with an eight-cluster pilot and only
expand when the host cells and integrity gates are sound.

## Why This Is Affordable Enough

The full target is an upper bound, not an instruction to repeat every task
indefinitely. Most tasks run once per paired cell. Only a small reliability
panel is repeated. Fault injection is deterministic and does not require extra
provider calls. Human review and independent implementation are stratified
samples, not a second full benchmark.

This gives a meaningful chance to detect medium-to-large paired effects while
keeping a clear statement that smaller effects require more clusters.

## What Actually Exists

| Output | Evidence level | Current state |
|---|---|---|
| Release replay | executed | Fails Hermes parity; not a benchmark result |
| Host conformance fixtures | executed | 16 focused tests pass; tests lifecycle integrity only |
| #84 paired harness | built/source-inspected | Sealed protocol exists on an unmerged branch; no sealed result |
| #268 design and reports | built | This change supplies the previously untracked documents |
| Formal Alpha2 comparison | not-run | Blocked on evaluator-owned holdouts, exact digests, host access, and reviewers |

## Important Choices

| Choice | Reason | Trade-off |
|---|---|---|
| Native host baseline | Separates RT benefit from host behavior | Requires clean per-host homes and extra baseline runs |
| 24 task clusters/host | Task clusters, not repeats, provide inference power | Full nine-cell run is larger than a smoke test |
| Five hidden holdouts | Prevents tuning to public fixtures | Requires an external evaluator authority |
| Host-specific analysis | Prevents one host hiding another's failure | No single pooled headline score |
| Hard gates separate from quality | A polished report cannot excuse false completion | Some attractive quality improvements will still fail release |

## Uncertainty

The formal run remains conditional. The design does not prove that Alpha2 is
better, and the retained release manifest currently proves the opposite for
required Hermes parity. The effect-size target is a planning assumption, not a
guaranteed result. If the pilot variance is high, the correct response is a
predeclared task-family expansion, not selective removal of difficult tasks.

## Next Visible Milestone

Issue #84 should first produce a source-bound sealed manifest containing the
native no-RT baseline, exact A1/A2 identities, the nine-cell matrix, 24 task
cluster digests, and five hidden holdout digests. The first executable milestone
is the eight-cluster pilot with a separate `pilot` disposition. No pilot output
may be copied into the formal release result.

## Human Decision Gate

- Status: pending evaluator authority and execution
- Design decision: selected
- Benchmark result: not claimed
- Required next evidence: sealed manifest, clean native baselines, pilot journal,
  paired analysis, blinded review, and independent implementation receipts
