## 1. Contract and red tests

- [x] 1.1 Add typed policy/proposal/delta/digest/replay fixtures and authority tests.
- [x] 1.2 Add six-component baseline, no-change, and attribution cases.
- [x] 1.3 Add digest lineage, contradiction, gap, malformed, and supersession cases.
- [x] 1.4 Add deterministic replay, calibration, pruning, obligation, and worker-rejection cases.
- [x] 1.5 Prove recursive worker/frontier/report/local-completion signals cannot close state.
- [x] 1.6 Run focused pytest plus Ruff check and format-check at each red slice.

## 2. Policy and delta

- [x] 2.1 Add typed normalized inputs, five proposal kinds, dispositions, scores, and traces.
- [x] 2.2 Implement deterministic ranking, tie-breaks, duplicate/dominance deferral, P0 exemptions, and calibration.
- [x] 2.3 Implement immutable six-component delta and explicit baseline/reference attribution.
- [x] 2.4 Run focused source/test pytest and Ruff gates with a source-bound receipt.

## 3. Digest and replay

- [x] 3.1 Emit schema-versioned classified statements, exact references, gaps, limitations, obligations, and lineage.
- [x] 3.2 Reject malformed, stale, duplicate, unsupported, or certainty-bearing inputs; retain read-only legacy projection.
- [x] 3.3 Prove replay equality, calibration isolation, deterministic seeds, and canonical input digests.
- [x] 3.4 Run focused insight/replay pytest and Ruff gates.

## 4. Recursive compatibility

- [x] 4.1 Translate local observations to policy proposals, deferrals, or blockers without lifecycle writes.
- [x] 4.2 Preserve read-only callers and reject worker/report/frontier completion authority.
- [x] 4.3 Run recursive regressions and changed-file Ruff gates.

## 5. Evidence and acceptance

- [x] 5.1 Record exact group 6/16 commands, SHAs, versions, seeds, and evidence paths.
- [ ] 5.2 Run focused/full pytest, strict OpenSpec, package, governance, delivery, and diff checks on the final head.
- [ ] 5.3 Review scope isolation and prepare one PR closing #58 only after executable evidence exists.
