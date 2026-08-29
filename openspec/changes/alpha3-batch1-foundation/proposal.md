# Proposal: alpha3-batch1-foundation

## Why

Alpha3 立项调研（`docs/evaluation/research/findings-reconciliation.md`，基线 `0aa67a7` = 已发布 0.1.0-alpha2）确认了两个结构性事实：

1. **行为层-运行时断层**：alpha2 周期建成的 ~25k 行治理机器（correction/contradiction/acceptance/13 态生命周期）在生产路径上零调用——`apply_correction`/`apply_contradiction` 的调用者只有 coordinator 自身与 tests；`skill-src/SKILL.template.md` 与 alpha1 仅差 27 行，`references/research-quality-playbook.md` 与 alpha1 逐字节相同。用户感受到的"机械、多轮漂移、跟 harness 对话"源于此。
2. **调度层平行世界**：`orchestration.py`（358 行，alpha1 遗产）零消费者仅剩 `__init__` re-export；`policy.py`/`AdaptiveResearchPolicy`（564 行，含 replay/calibrate）仅有测试调用、未接入 `coordinator.dispatch`。每个治理周期在旧调度层旁盖新楼，不收敛则后续所有 alpha3 能力（含 #334 best-N）将落在第四个平行层上。

同时，剩余 ~21 个 alpha3 issue 的排序缺乏证据：质量损失发生在哪个管线阶段（alignment/evidence/synthesis/delivery）只有口述，无归因。发布治理语言仍含"open benchmark → cannot release"类与 rolling-Alpha 政策矛盾的绝对化表述（issue #331）。

本 change 是 alpha3 第一批（4 issues：#332 #333 #335 #331），执行计划见 `.claude/PRPs/plans/alpha3-batch1-pilot-navigated-sprint.plan.md`（已确认）。试点（#335）的归因输出决定第二批范围。

## What Changes

四个能力交付（一 issue 一分支一 PR，worktree 隔离，TDD+SDD）：

1. **行为层协议接线（#332, P0）**：SKILL.template.md / research-quality-playbook.md / 三 host adapter 新增 4 个行为协议段（被打断→`record_correction` 二选一；结论被质疑→`apply_contradiction`；交付后→acceptance 5 决议收集；对齐期→意图声明按 claim 抽取），并新增行为层↔runtime 契约测试——文档按名引用的每个 API 必须在 `src/research_tree/` 真实存在且签名匹配。
2. **调度权威收敛（#333, P1）**：摘除死层 `orchestration.py`；将 `AdaptiveResearchPolicy` 接入 `coordinator.dispatch` 决策路径（保留 replay/calibrate 能力）或按 ADR-006 显式退役迁移；packages/ 文档词汇清洗（orchestration 词汇→coordinator/policy）；产出 ADR-006 单一调度权威决策。
3. **有界配对试点（#335, P0）**：alpha1（`0.0.1-a1`）vs alpha2（`0aa67a7`）两臂、8-12 案例（四领域、非 holdout）、单模型单 host、4 阶段盲评 rubric；产出 `docs/evaluation/research/pilot-report-v1.md` 阶段归因报告，显式声明不可下结论的范围。
4. **发布治理语言对齐（#331, P1）**：`docs/governance/*` 区分"包发布/Alpha 试点适用/组织推广/无人值守最终权威"四档声明；消除与 rolling-Alpha 政策矛盾的绝对化表述。

## Capabilities

### New Capabilities
- `behavioral-runtime-protocols`: 行为层（SKILL/playbook/adapters）与 runtime 治理 API 的绑定协议与契约测试——被打断、矛盾、验收、claim 抽取四个交互场景必须走具名 runtime API，禁止散文应付。
- `bounded-paired-pilot`: 有界配对评测资产（manifest/案例族/rubric/报告格式）与阶段归因方法——A1 vs A2 质量损失按管线阶段归因的最小可复现程序。
- `release-governance-tiers`: 发布治理的四档声明语言与 per-issue gate 声明格式。

### Modified Capabilities
- `scheduling-authority`: （现为 alpha2 事实行为，无既有 spec 文件）调度从三平行层收敛为单一权威——`compile_orchestration_plan` 从公共 API 摘除，`AdaptiveResearchPolicy` 进入 dispatch 生产路径。

## Impact

- **代码**：删除 `src/research_tree/orchestration.py`（358 行）；修改 `policy.py`/`coordinator.py`（dispatch 接线）/`__init__.py`（导出面）；无 claims/contradictions/closure 语义改动（已验证为正确资产）。
- **行为层文档**：`skill-src/SKILL.template.md`、`references/research-quality-playbook.md`、三份 `skill-src/*-adapter.md`；packages/ 三份经 `build_skill_packages.py` 重生成。
- **新资产**：`tests/test_behavioral_layer_contract.py`、`docs/adr/ADR-006-single-scheduling-authority.md`、`evaluation/pilot/*`、`docs/evaluation/research/pilot-report-v1.md`、`docs/governance/*` 修订。
- **流程**：4 分支 4 PR（squash 合入，顺序 331→332→333→335，#333 rebase on #332）；每 PR 质量门 = CI `delivery-governance.yml` 的本地等价全量命令。
- **不做**：#314-#318/#324 认知模型系（等试点证据）、#334 best-N（依赖本收敛）、coordinator 大拆分、全量 benchmark #84。
