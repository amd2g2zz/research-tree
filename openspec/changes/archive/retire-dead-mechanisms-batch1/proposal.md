# Proposal: retire-dead-mechanisms-batch1

## Why

GitNexus 调用图审计（issue #420，索引 13721 符号，2026-08-31）确认 12 个模块零生产
CALLS 边（调用者仅自身 / tests / `__init__` re-export），文本 grep 交叉确认。四个 alpha2
headline 特性（#320 state projection、#329 progress delta、#330 operating model、#334
best-of-n）合入后从未接线，重复了 alpha2 行为层-运行时断层在 runtime 内部的模式。删除先例：
ADR-006 在同一证据标准下整文件删除 `orchestration.py`。

## What Changes

- **BREAKING**: 删除 12 个图验证死模块及其 `__init__` re-export 与专属测试：
  `alpha1_adversarial.py` `best_of_n.py` `black_box_regression.py` `progress_delta.py`
  `state_projection.py` `operating_model.py` `cognition.py` `growth.py`
  `native_workflows.py` `shared_brief.py` `context_cost.py` `schemas.py`。
- 摘除 `problem_forest.py` 的死 `cognition` import（TYPE_CHECKING 注解残留）。
- 摘除 `coordinator.py` `confirm_handoff` 的 growth-aware opt-in 参数 `branch` 及其 payload
  分支（F3）；`alignment_protocol.py` 摘除 `growth` import 与 `growth_aware_readiness` 方法
  （growth 死链的仅存生产引用点）。
- alpha2 治理注册表 group 61 的 `acceptance_command` 与 `command_receipt.command` 摘除已退役
  `src/research_tree/native_workflows.py` 路径（其余能力入口不变）。
- `tests/test_context_ledger.py` 摘除 `context_cost` 引用（幸存模块的专属测试，仅摘引用）。

## Capabilities

### New Capabilities

- `dead-mechanism-retirement`: 图验证死机制的证据标准与退役契约——零生产 CALLS 边 +
  grep 零真引用双确认，删除后零断裂引用（无 re-export、无死 import、无注册表悬空路径）。

### Modified Capabilities

（无既有 spec 文件声明本批模块为能力面；delivery-matrix 中 host-native-orchestration
与 canonical-host-event-boundary 的 `source_modules` 已摘除 native_workflows 路径，
native_workflows 的退役由本 change 记录。）

## Impact

- **代码**：删除 `src/research_tree/` 下 12 个模块（约 1,418 行）与 11 个专属测试文件；
  `__init__.py` 摘除 3 个 import 块与 16 个 `__all__` 条目；`coordinator.py`/
  `alignment_protocol.py`/`problem_forest.py` 摘除断裂引用点。
- **治理**：`openspec/changes/unify-research-runtime-alpha2/registries/` 的
  task-execution-v1.json 与 task-verification-v1.json（group 61 命令对）摘除退役模块路径。
- **不改动**：ADR-007 pydantic 依赖与 boundary 政策保留（`schemas.py` 退役后 ADR-007 中
  `src/research_tree/schemas.py` 路径表述转历史，后续 batch 处置）；user-owned 数据零操作。
