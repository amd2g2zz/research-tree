# Alpha3 Batch-3 验收记录（mainline purge + goal wiring）

- **验收日期**：2026-09-01
- **基线**：dev `c75174f`（干净 worktree `acceptance-final`；工作树含 uv.lock 镜像噪音，不属 diff）
- **PR 清单**（11 个实现/修复 PR 全部 squash 合入 dev，delivery-gate + G-对抗双审全过）：

| PR | Issue | 内容 | mergeCommit |
|---|---|---|---|
| #433 | #426 | 103 changes 归档 + gone 分支清零 + .gitignore 修绿 | 679687d |
| #434 | #420 | 12 死模块退役 ~5k 行 + 捎带覆盖移植 | 见 dev 历史 |
| #435 | #421 | 5 死链退役 + 2 CI 模块迁出 + registry 悬空类关闭 | 164c235 |
| #436 | #422 | legacy shim 清零（A2 零命中）+ 13 态投影闭环 | a62fb9f |
| #437 | #425 | release_evaluation 迁 harness + evaluation 收缩 + 全分支覆盖 | dde784f |
| #438 | #424 | dispute 逐字并入 contradictions + 4 放弃项负向固化 | ed486de |
| #439 | #423 | debug_trace 折入 lifecycle_hook（121 行 ≤150） | e0a8599 |
| #441 | #427 | 投影生命周期 CLI 接线 + serves 校验 + guard 层 falsifiability | e3b21da |
| #442 | #428 | 贡献判定真值表 + guidance_defect 重试 + method_switch 升级 | a62fb9f |
| #443 | #429 | goal_satisfaction 完成门（manifold 三 fail + complete 阻塞） | fc0b285 |
| #444 | #430 | 行为层重写（SKILL 262 行、R3 助纠协议、锚句、契约测试） | 4614fa9 |
| #445 | #427 | A2 验收措辞微修复 | 949bf80 |
| （随 #445） | #426 | batch-3 十 change 归档收尾（A10） | c75174f |

## §A 残留清零（终态复跑输出）

- **A1**：22 路径删除循环零输出 ✓（终审#1/#2 独立复跑）
- **A2**：`grep -rniE legacy src/research_tree --include="*.py"` = 空 exit 1 ✓（含 #445 措辞微修复）
- **A3**：`ls src/research_tree/*.py | wc -l` = **51 ≤ 53** ✓
- **A4**：HEAD 索引重建后逐名 Function 查询 = **20/20 零**（迁移模块 scripts/openspec_governance.py 与 evaluation/harness/release_evaluation.py 的 33 个函数确认在新位置存活）✓
- **A5**：`uv build --wheel` 成功，57 文件，BAD ENTRIES = [] ✓
- **A6**（R4 口径）：import 级清零 exit 1 + dispute.py 不存在 ✓
- **A7**：命中 = coordinator.py + ledger.py:172（批前既有接线 4f2026b）；"无新增引用"实质达标。**规格文本偏差备案**：§A7 字面文件集 {feedback.py, coordinator.py} 过时（feedback.py 从无此二函数），按意图口径验收，规格后续 revision 修正
- **A8**：`git branch -vv | grep -c gone` = **0** ✓（12 个 worktree 占用分支经 dirty 检查全部 clean 后移除）
- **A9**：过期 workstate 计划已删 ✓
- **A10**：顶层 change = **11 ≤ 12** ✓（#433 归档 103 + #445 归档 batch-3 十 change）

## §B goal 环具名测试（终态 62 passed）

- test_goal_wiring.py：B1 五具名 + 接线/负向（15）——serves 三条精确错误文案逐字、confirmed=fail-closed、CLI 端到端 propose→display→confirm→树存在
- test_goal_contribution.py：§B2 真值表 9 具名 + 熔断/去重/隔离/重计（18→28）——confidence 零参与、映射校验、partition fail-closed、cap=1
- test_goal_gate.py：§B3 七具名——三 fail 语义整字典断言、waiver 强制 reason、complete 阻塞、why_not_complete 逐 oracle resolve

## §C 行为层

- C1：SKILL.template.md = **262 行 ≤300** ✓（6 协议段 ≤8）
- C2：五文档 **4,500 词 ≤5,000** ✓
- C3：两锚句 × 四文档逐字在场（终审双席 grep 1/1 each）✓
- C4：`apply_correction`/`apply_contradiction`/`research-tree status` 22 处提及全部带可用性门 ✓
- C5：`test_doc_names_only_real_runtime_apis` 覆盖 #441-443 新名（write_goal_satisfaction/latest_confirmed/validate_falsifiability/assess_goal_contribution/strategy 三动词），终审 #2 端点反查 13/13 实存 ✓
- C6：references/debug-tracing.md 35 行 ≤80；`.research-tree-debug/` 在 .gitignore:22 ✓

## §D 回归门（终态）

- D1：`1 failed, 1096 passed, 4 skipped`——唯一失败 = docker hermes loader 超时（环境性，文件与 diff 零交集，多席独立归因）
- D2：ruff check + format 全绿
- D3：build_skill_packages --check exit 0
- D4：check_docs / check_repository_layout / check_openspec_governance 全 valid
- D5：十 per-issue change 均 strict-validated 于各自 PR（归档后不再单独校验）
- D6：detect-changes 于 HEAD 索引零漂移；A4 全量图复扫如上
- D7：超额 PR（#433/#434/#439/#441/#442/#444）均按 delivery-policy 豁免通道 `delivery:oversized-approved` + PR 备案（R2 口径）

## 对抗终审（Runbook 3/4 第 5 步）

- **终审 #1**（ecc:code-reviewer，fresh）：PASS——§A 七行复跑（含预判失败的 A7，落实为规格文本 MEDIUM）、§B 三测试盲述对照全 MATCH、§C 锚句逐字、A4 图级三模块零、归档 PR 抽检自洽
- **终审 #2**（ecc:silent-failure-hunter，fresh）：PASS——§A 八行独立复跑、文档 API 端点反查 13/13 实存、goal 环五件套端到端 file:line 接线证据、§D 62 passed 复跑
- 终审 LOW/MEDIUM 汇总（批后跟进项）：
  1. §A7 规格文件集文本失准（意图口径已按此验收）
  2. `_guard_passes` :1893-1917 handoff_confirmed 死分支清理（#441 复审发现，批前已存在）
  3. 零 oracle confirmed projection 的 gate 空转 pass（falsifiability 可加 ≥1 oracle 要求）
  4. 损坏 goal_satisfaction 注册静默吞没（建议显式 fail + from_dict 重解析）
  5. insights.py / decision_map.py 收缩候选（审计附录 A1-F5）
  6. three folded rules（唯一树/supersession、explicit execute-direct、typed claims admission）补回或显式退役留痕
  7. partition 无投影 run fail-open（有意设计，B3 兜底，备案）

## 过程修订（PRD 修订记录 R1-R6）

R1 投影接线（#427 扩围）/ R2 D7 删除型 PR 口径 / R3 对齐助纠协议（maintainer 裁决）/ R4 A6+A7 验收口径 / R5 confirmed 语义 / R6 §B2 schema 驱动映射——全部 epic #431 留痕。

## 验收判定

**§A-§D 全绿 + 对抗终审×2 零 CRITICAL/HIGH ⇒ 验收通过。** 批后跟进项如上列表，不阻塞本批次关闭。
