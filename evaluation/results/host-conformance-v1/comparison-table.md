# Host-Conformance v1 — Prior Attempt Supersession

| Prior attempt | Non-acceptance reason | Superseding receipt |
|---|---|---|
| #82 cross-host tests (synthetic capability observations, `tests/test_native_dynamic_workflows.py@6a7b89c`) | capability strings, no host-native worker surface, no live binding | `.research-tree/evaluation-runs/issue-244/codex-mode/result.json` + `hermes-mode/result.json` + `claude-modes/*-result.json` (real processes, real identities) |
| Hermes hook test with manually constructed payload (`tests/test_hermes_skill_compatibility.py@6a7b89c`) | payload was hand-authored, not host-fired | hermes Docker runs in `issue-244/hermes-mode/` (native delegate_task, pinned image digest) |
| Adapter test with manually written Finding Packs (`tests/test_native_execution_adapter.py@6a7b89c`) | packs were authored, not host-produced | negative-oracle cells in every mode result (synthetic-finding rejected) |
| #241 pre-blocker deterministic bridge (`~/rt-241-handoff-20260818.patch`) | fail-closed bridge without live child-ID binding | issue-244/codex-mode receipts (4 real call identities) + #266 merged bridge |
| Native-Docker #84 pilot (`agent/issue84-docker-envelope`) | topology smoke without canonical receipts; host parity unproven | issue-244 all-modes matrix (5/5 passed cells incl. fault + replay) |

All prior pilots remain non-acceptance evidence; none was silently promoted.
