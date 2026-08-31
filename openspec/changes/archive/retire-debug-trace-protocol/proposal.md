# Proposal: retire-debug-trace-protocol

## Why

GitNexus 调用图审计（issue #423，2026-08-31）确认 `src/research_tree/debug_trace.py`
（1,634 行，runtime 最大模块）唯一生产 CALLS 边是 `lifecycle_hook.observe` 的
fail-open `emit_trace` 调用；其余 18 条边均为模块内自引用。协议/回放/脱敏机制
（`CausalTraceService`、`research-tree-debug` CLI、phase/code 词表校验 CLI 面）
是过渡期诊断脚手架，已超出"可旁路侧信道"的用途。alpha3 zero-compat 裁定：
能力随模块退役，不保留兼容面。

## What Changes

- **BREAKING**: 删除 `src/research_tree/debug_trace.py`（1,634 行）与
  `research-tree-debug` CLI 入口（pyproject `[project.scripts]`）；
  trace 协议、`CausalTraceService` 回放/解释面、`summarize_traces` 汇总命令
  随模块退役，不保留 schema/replay 兼容（zero-compat）。
- `emit_trace` 及其最小依赖闭包（常量、根/路径/标识符/codes 校验助手、原子写）
  折入 `src/research_tree/lifecycle_hook.py`（约 130 行，≤150 行预算）；
  函数体逐字等价，仅内部助手按 `_trace_` 前缀重名以免与既有 hook 助手冲突；
  `observe(debug=True)` 路径行为不变，trace 失败仍被 `(OSError, ValueError)`
  吞掉，绝不阻塞宿主会话。
- 删除 `tests/test_debug_trace.py` 与 `tests/test_replay.py`（replay 能力随模块
  退役）；3 个仍锚定 emit_trace 行为的用例迁入 `tests/test_lifecycle_hook.py`
  （其中 1 例的 `summarize_traces` 段随能力退役，用例相应收窄并更名）。
- `references/debug-tracing.md` 重写为 emitter-only（35 行，≤80 行上限）；
  `skill-src/SKILL.template.md` 与 `hermes-SKILL.template.md` 的 debug 段落对齐
  （不再 gate 在已退役 CLI 上）；`docs/guides/operator.md` Debug Tracing 段落
  对齐；host 包再生成。
- 治理 registry（#420/#421 成对摘除/改指先例）：task-execution-v1 与
  task-verification-v1 的 group 11/36/45/63 命令对成对摘除退役路径（每对两侧
  保持逐字相同；receipt 摘要/时间戳为历史记录不改写）；delivery-matrix-v1 的
  `runtime-observability` 行改指 `lifecycle_hook.py`、
  `semantic-replay-reconstruction` 行摘除退役符号；repository-paths-v1 的
  `.research-tree-debug/` 行 `canonical_command` 改指 `research-tree-hook
  --debug`。
- `.gitignore` 已含 `.research-tree-debug/`（确认在位，无需改动）。

## Capabilities

### New Capabilities

- `debug-trace-protocol-retirement`: emitter-only 契约——trace 发射收敛为
  lifecycle_hook 内单一 fail-open writer（≤150 行），无协议对象、无回放、
  无独立 CLI；记录仅含有界脱敏字段；治理命令对与文档零残留。

### Modified Capabilities

（无既有 spec 文件声明 debug-trace 为能力面。）

## Impact

- **代码**：删除 `src/research_tree/debug_trace.py`（1,634 行）；
  `lifecycle_hook.py` 折入约 130 行 emitter 闭包；pyproject 摘除 1 个
  script 入口。
- **测试**：删除 2 个专属套件（`test_debug_trace.py` 248 行、
  `test_replay.py` 约 260 行）；迁入 3 个 emit_trace 用例（1 例收窄）。
- **文档**：`references/debug-tracing.md` 重写（64 → 35 行）；
  `docs/guides/operator.md`、两个 SKILL 模板段落对齐。
- **治理**：4 个 registry 文件共 11 行（命令对 8 行、delivery-matrix 2 行、
  repository-paths 1 行）。
- **不改动**：lifecycle hook 观测行为与 fail-open 语义、
  `.research-tree-debug/` 目录位置与 gitignore、既有 13-state 区域投影、
  dispute/contradictions/release_evaluation/evaluation 辖区（#424/#425）。
