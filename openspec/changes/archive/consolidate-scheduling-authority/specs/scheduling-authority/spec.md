## ADDED Requirements

### Requirement: 调度权威必须收敛为单一模块

"下一步做什么研究"的决策必须由唯一模块拥有：`coordinator`（配合接入生产路径的 policy 提案）。`orchestration` 层从公共 API 摘除并删除。

#### Scenario: orchestration 不再可从公共 API 导入
- **WHEN** 任何代码尝试 `from research_tree import compile_orchestration_plan`（或 `validate_orchestration_plan`）
- **THEN** 导入失败；全库（src/tests/docs/packages）无对 orchestration 模块的残留引用

#### Scenario: policy 提案进入 dispatch 生产路径
- **WHEN** `coordinator.dispatch` 在策略投影确认点做出派发决策
- **THEN** `AdaptiveResearchPolicy.propose` 的输出被消费（作为派发依据并记录于 attempt lineage）；无提案可用时保持既有行为，不失败

#### Scenario: 备选结局——policy 退役迁移同样满足收敛
- **WHEN** TDD 接线测试证明 dispatch 语义与 PolicyProposal 产物不匹配
- **THEN** 按 ADR-006 的退役分支执行：replay/calibrate 能力迁移至 coordinator 侧，policy.py 删除，收敛验收（单一权威）不变

### Requirement: 收敛决策必须以 ADR 记录

#### Scenario: ADR-006 内容完整性
- **WHEN** 阅读 `docs/adr/ADR-006-single-scheduling-authority.md`
- **THEN** 含：保留层与退役层、能力迁移映射（4-phase 概念在 coordinator 的对应物或显式弃用理由）、备选方案与否决理由、回滚条件

### Requirement: 文档词汇不得指向不存在的调度模块

#### Scenario: 行为层文档与调度权威一致
- **WHEN** packages/ 与 skill-src 文档描述调度/波次行为
- **THEN** 引用 coordinator/policy 词汇；提及 orchestration 的段落被重写或删除
