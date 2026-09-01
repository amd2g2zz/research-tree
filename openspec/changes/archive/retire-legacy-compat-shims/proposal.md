# Proposal: retire-legacy-compat-shims

## Why

alpha3 zero-compat ruling (issue #422): historical baggage must not exist — not
"as little as possible". Grep + call-graph audit of `src/research_tree` found 11
live compat shims: a dual-schema readiness payload acceptance, a legacy human
delivery kind detection branch, `legacy_unspecified` evidence-class branches in
three modules, a rename map in the completion obligations, a legacy lifecycle
translation table under `self_state`, a non-canonical `ingest_event` wrapper in
front of the one canonical HostEvent ingress, a legacy belief-status vocabulary
plus translation map in `speech_acts`, a second dead legacy-status set in
`alignment_protocol`, dual anchor rendering in delivery, a sentinel trigger
label, and an old-workspace auto-migration machinery. Git history is the
compatibility story; the runtime carries none of it.

## What Changes

- **BREAKING**: `acceptance.py` deletes `LEGACY_HUMAN_KIND` and its detection
  branch; non-canonical human delivery kinds raise the single
  non-canonical-kind acceptance error.
- **BREAKING**: `evidence.py` and `closure.py` delete the `legacy_unspecified`
  evidence-class rejection branches; evidence artifacts carry only explicit,
  current evidence classes and no sentinel is special-cased anywhere.
- **BREAKING**: `readiness.py` validates the readiness record payload against
  the current schema only — `risk_verification` and `failure_category` are
  required keys; the five-key payload shape and six-key diagnostic shape are no
  longer accepted.
- **BREAKING**: `project_workspace.py` deletes `RUN_BOUND_LEGACY_ROOTS`,
  `UNATTRIBUTED_LEGACY_ROOTS`, `_assert_no_unattributed_legacy_root`, and
  `_migrate_legacy_roots`; `initialize` no longer migrates old-format run
  workspaces and the manifest no longer carries `migrated_legacy_roots`.
  Accepted consequence (maintainer ruling): old-format run workspaces must be
  recreated or migrated manually; on-disk user data is unaffected.
- `coordinator.py` deletes the `insight_ref` → `insights_non_blocking` rename
  maps (obligations report the completion-manifold field name directly), the
  `_legacy_to_regions` translation table (regions project from the canonical
  state via `_state_regions`, which fails closed with `IllegalTransitionError`
  for states without a canonical region projection), and the non-canonical
  `ingest_event` wrapper (canonical HostEvent ingress only).
  `debug_trace.py` reports the same single obligation name.
- `speech_acts.py` deletes `LEGACY_BELIEF_STATUSES`, `STATUS_LEGACY_MAP`, and
  the translation branch in `normalize_status` (single status vocabulary;
  unrecognized values keep the warn-and-default-to-candidate policy).
  `alignment_graph.py` checks node statuses against its own unified
  `NODE_STATUSES` vocabulary before falling through; `alignment_protocol.py`
  deletes its dead `_LEGACY_BELIEF_STATUSES` set and `_is_legacy_status`.
- `delivery.py` renders strict typed evidence anchors only in the finding
  table; the semantic-anchor branch of `_anchor_label` is deleted (decision
  anchor templates remain validated and rendered by `_anchors`).
- Wording-only purge of the retired word in comments, docstrings, a
  continuation trigger label (`recursive_search.py`), and a skill conflict
  reason code (`skill_setup.py`).

## Capabilities

### New Capabilities

- `legacy-compat-shim-retirement`: zero-compat contract for the alpha3
  runtime — no dual-schema acceptance, no rename maps, no sentinel branches,
  no non-canonical ingress wrappers, no old-workspace auto-migration; the
  grep gate `grep -rniE legacy src/research_tree --include=*.py` stays empty.

### Modified Capabilities

（无既有 spec 文件声明上述 shim 为能力面；`canonical-state-regions` 的
self_state 五区域投影行为保留，仅其实现不再携带旧状态翻译表。）

## Impact

- **代码**：11 个 shim 点分布于 `acceptance.py`、`alignment_graph.py`、
  `alignment_protocol.py`、`closure.py`、`coordinator.py`、`debug_trace.py`、
  `delivery.py`、`evidence.py`、`project_workspace.py`、`readiness.py`、
  `recursive_search.py`、`skill_setup.py`、`speech_acts.py`。
- **测试**：旧行为测试删除 5 个（两个工作区迁移测试、未归因迁移根守卫测试、
  旧证据类拒绝测试、旧证据不可发 token 测试）；翻转 4 个（旧 kind 拒绝消息、
  旧 readiness schema 必须被拒、两个 ingest 守卫测试调用点收敛到 canonical
  ingress）、以及完成义务名/调试追踪义务名断言跟随单一字段名。
- **文档**：README Quick Start 增加一行 breaking 说明（旧运行工作区不再自动迁移）。
- **不改动**：`canonical-state-regions` 投影行为、`alignment_graph` 就绪判定、
  严格证据锚渲染断言、user-owned 数据零操作。
