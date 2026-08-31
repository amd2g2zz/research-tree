# Proposal: retire-dead-mechanisms-batch2

## Why

GitNexus 调用图审计（issue #421，2026-08-31）确认 7 个模块零生产 CALLS 边（调用者仅
自身 / tests / `__init__` re-export），grep 交叉确认。删除前例：ADR-006 整文件删除
`orchestration.py`；batch1（#420）同标准退役 12 个死模块。本批是 alpha3 死链清理第二波。

预扫修正的两处迁出（非删除）：
- `openspec_governance.py`：CI `delivery-gate` 经 `scripts/check_openspec_governance.py`
  硬依赖该模块，迁至 `scripts/`（纯 CI 工具，非 runtime）。
- `context_ledger.py`：epic 预扫判定"adapter fallback 目标不存在"有误——该模块经
  `COMMON_FILE_MAP` 生成进全部三个 skill 包（`scripts/context_ledger_contract.py`，
  且为 Hermes 可执行闭包的 entrypoint），packaged context-receipt 子命令是被
  `tests/test_native_execution_adapter.py` 与 `tests/test_hermes_execution_adapter.py`
  覆盖的活行为。迁至 `scripts/context_ledger_contract.py` 并把 adapter 改为直连
  import（src 依赖清零，行为与测试原样保留，包产物字节不变）。

## What Changes

- **BREAKING**: 删除 5 个图验证死模块及其 `__init__` re-export 与专属测试：
  `assurance.py` `preferences.py` `alignment_protocol.py`
  `durable_interaction_state.py` `interaction_state.py`。
- **BREAKING**: lifecycle 事件不再镜像写入 durable interaction state
  （`lifecycle_hook` 的 durable try 块摘除；事件流记录行为不变）。
- 迁出 2 个有活消费者的模块：`openspec_governance.py` → `scripts/`，
  `context_ledger.py` → `scripts/context_ledger_contract.py`；`src/` 路径清零目标
  不变，三个 governance 测试套件与 context ledger 套件随迁（scripts-path 先例）。
- alpha2 治理注册表 group 7 / 23 / 29 的 `acceptance_command` 与
  `command_receipt.command` 成对摘除已退役路径（#420 先例）；
  delivery-matrix 的 `project-user-preference-profile` 行摘除退役
  `source_modules` 路径。
- 幸存测试套件中 alignment_protocol / durable 专属用例摘除；`research_tree`
  包根不再 re-export 任何被删符号。

## Capabilities

### New Capabilities

- `dead-mechanism-retirement`: 图验证死机制的证据标准与退役契约（batch2 范围）——
  零生产 CALLS 边 + grep 零真引用双确认，删除后零断裂引用；有硬消费者的模块以
  relocation 退役并如实记录。

### Modified Capabilities

（无既有 spec 文件声明本批模块为能力面。）

## Impact

- **代码**：删除 `src/research_tree/` 下 5 个模块（约 3,661 行）与 8 个专属测试文件
  （约 1,741 行）；`__init__.py` 摘除 4 个 import 块与 49 个 `__all__` 条目；
  `lifecycle_hook.py` 摘除 durable 镜像块；幸存测试套件摘除 7 个退役专属用例；
  迁出 2 个模块（约 1,032 行，字节不变移动 + import 修补）。
- **治理**：task-execution-v1.json / task-verification-v1.json group 7/23/29 命令对、
  delivery-matrix-v1.json source_modules。
- **不改动**：speech_acts.py / alignment_graph.py / alignment_handoff.py（本批不动）；
  user-owned 数据零操作；durable interaction state 已写入的历史文件不迁移不删除。
