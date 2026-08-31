# Proposal: migrate-release-evaluation-harness

## Why

GitNexus 调用图 + grep 双审计（issue #425）确认：
`src/research_tree/release_evaluation.py` 的 6 个再导出符号（IntegrityGate,
InvalidReleaseManifest, ReleaseCaseResult, ReleaseDecision, ReleaseManifest,
evaluate_release）在 src/ 生产代码零消费——唯一真实消费者是 harness 入口
`evaluation/harness/run_release_gates.py`（经根包 umbrella 再导出导入）。
evaluation.py（701 行）的生产消费面经逐一符号 grep 精确认定为 2 个符号：
`BLUEPRINT_EVALUATION_KIND` 与 `validate_blueprint_evaluation_payload`
（由 `completion_inputs.write_evaluation` 延迟导入消费；issue 正文所列
readiness/run_ledger 实测零符号级消费，仅有 "evaluation"/"blueprint-evaluation"
字面量无 import）。其余 suite/runner/protocol/5 dataclass 无生产调用者。

## What Changes

- **BREAKING**: `src/research_tree/release_evaluation.py` 从 runtime 包移除，
  字节不变迁移至 `evaluation/harness/release_evaluation.py`（evaluation-paths-v1
  已登记 `evaluation/harness/` 为 tracked evaluator-code）。不设 alias/shim。
- **BREAKING**: 根包不再再导出 IntegrityGate, InvalidReleaseManifest,
  ReleaseCaseResult, ReleaseDecision, ReleaseManifest, evaluate_release。
- `run_release_gates.py` 改为导入 harness 同级模块（run_host_conformance
  同级导入先例），registry entrypoint 命令文本不变。
- evaluation.py 收缩至被消费的验证面（701 → 400 行）：保留
  BLUEPRINT_EVALUATION_KIND、EvaluationError 层级、TimeSplitCase、
  EvaluationDiagnosis、validate_blueprint_evaluation_payload 及其验证辅助；
  删除 BlueprintEvaluationSuite、EvaluationCheck、
  IndependentEvaluationRequest/Result、IndependentImplementationRunner、
  SimplerBaselineResult 及 7 个 suite 专属辅助函数。
- `__init__` 再导出面收缩：release 再导出块摘除；evaluation 块保留 6 个幸存
  符号；`__all__` 摘除 12 个退役条目。
- 测试随迁：test_black_box_release.py 与 test_release_manifest.py 采用 harness
  sys.path 先例导入新位置；test_evaluation_suite.py 保留 2 个幸存用例
  （公共 case set 契约 + TimeSplitCase 隐匿材料拒绝），摘除 5 个 suite 专属
  死用例。

## Capabilities

### New Capabilities

- `release-evaluation-harness`: evaluator 持有的 release gate 校验逻辑属于
  harness 资产而非 runtime 包；runtime 包零 re-export，harness 入口导入同级
  模块，registry entrypoint 命令保持原文本。

### Modified Capabilities

（无——evaluation-paths-v1.json 已将 `evaluation/harness/` 登记为 tracked
evaluator-code，entrypoint 命令路径全部指向 evaluation/harness/，零注册表改动。）

## Impact

- **代码**：迁移 1 个模块（375 行，字节不变）；evaluation.py 701 → 400 行；
  `__init__.py` 摘除 1 个 import 块（-8 行）+ evaluation 块收缩（-6 行）+
  12 个 `__all__` 条目摘除；`run_release_gates.py` 1 行 import 修补
  （迁移模块的直接消费者，改动即迁移本体）；3 个测试文件随迁/收缩
  （test_black_box_release.py 头部 8 行、test_release_manifest.py 头部 4 行、
  test_evaluation_suite.py 319 → 74 行）。
- **治理**：零注册表改动——所有引用 release gate 入口的 registry 命令
  （evaluation-paths-v1 entrypoints、task-execution/verification group 12 命令对）
  均指向 `evaluation/harness/run_release_gates.py` 脚本路径，脚本仍在原路径。
- **不改动**：claude_glm_regression / host_conformance / run_claude_glm_regression
  / run_host_conformance 等 harness 既有资产（零 diff）；#423（lifecycle_hook/
  debug_trace）与 #424（dispute/contradictions）辖区零交集。
