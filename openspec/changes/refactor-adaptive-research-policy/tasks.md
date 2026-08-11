## 1. Contract and red tests

- [x] 1.1 Add typed policy, proposal, delta, digest, and replay fixtures and
  register the exact authority boundary in `tests/test_adaptive_policy.py`.
- [x] 1.2 Add failing six-component baseline, no-change, and attribution cases
  in `tests/test_evidence_delta.py`.
- [x] 1.3 Add failing classified Insight Digest lineage, contradiction, gap,
  malformed-input, and supersession cases in `tests/test_insights.py` and
  `tests/test_insight_digest.py`.
- [x] 1.4 Add deterministic replay, calibration-version, pruning, mandatory
  obligation, and worker-suggestion rejection cases in
  `tests/test_policy_replay.py`.
- [x] 1.5 Add recursive-search authority-bypass red tests proving worker return,
  empty frontier, report shape, and local completion cannot close a Slot or run.
- [x] 1.6 At each red slice run focused pytest plus `uv run ruff check` and
  `uv run ruff format --check` over the new test files; record expected red
  failures without weakening the contract.

## 2. Pure policy and delta implementation

- [x] 2.1 Add `src/research_tree/policy.py` value objects for normalized inputs,
  five proposal kinds, deferrals/rejections, score components, and audit trace.
- [x] 2.2 Implement deterministic selection, tie-breaking, duplicate and
  dominance deferral, P0 exemptions, failure reweighting, and versioned
  calibration without persistence or lifecycle mutation.
- [x] 2.3 Replace scalar evidence delta behavior with an immutable six-component
  vector and explicit baseline/reference attribution in `evidence_delta.py`.
- [x] 2.4 Run focused policy/delta tests and Ruff lint/format checks over every
  changed source and test file; keep the receipt source-bound.

## 3. Insight Digest and replay

- [x] 3.1 Upgrade `insights.py` to emit schema-versioned classified statements,
  exact Finding Pack/Slot references, contradiction and gap signals, policy
  obligations, limitations, and previous digest lineage.
- [x] 3.2 Reject malformed, stale, duplicate, unsupported, or certainty-bearing
  digest inputs before policy consumption; preserve the legacy projection as a
  read-only compatibility view.
- [x] 3.3 Prove replay equality and calibration isolation in the digest and policy
  suites, including deterministic seeds and canonical input digests.
- [x] 3.4 Run focused insight/replay pytest plus Ruff lint and format checks over
  all changed insight, delta, policy, and test files.

## 4. Recursive compatibility demotion

- [x] 4.1 Refactor `recursive_search.py` to translate local observations into
  policy proposals, deferrals, or blockers without persisting Slot status,
  delivery manifests, or run completion.
- [x] 4.2 Preserve read-only compatibility for existing callers and make local
  report/task/frontier/worker signals explicitly non-authoritative.
- [x] 4.3 Run the recursive-search regression suite and changed-file Ruff lint
  and format checks; capture authority-bypass evidence.

## 5. OpenSpec and acceptance evidence

- [ ] 5.1 Update group 6 and group 16 task/verification registries with exact
  focused pytest and Ruff commands, commit SHA, policy version, seed, and
  evidence paths.
- [ ] 5.2 Run focused policy/delta/insight/replay/recursive tests, full pytest,
  strict OpenSpec, package parity, governance, delivery validation, and
  `git diff --check` on the exact branch head.
- [ ] 5.3 Review the diff for scope isolation, mark completed tasks only after
  executable evidence exists, and prepare one PR closing #58.
