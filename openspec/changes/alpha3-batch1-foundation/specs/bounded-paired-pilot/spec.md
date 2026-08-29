## ADDED Requirements

### Requirement: 试点资产必须满足身份与可复现纪律

有界配对试点的 manifest 必须记录两臂身份（arm: alpha1@`0.0.1-a1` / alpha2@`0aa67a7`）、同一 model revision、同一 host、案例集版本、rubric 版本、seed 与重复策略，且可从干净 worktree 重建。

#### Scenario: manifest 缺身份字段时拒绝执行
- **WHEN** 试点 manifest 缺任一必需字段（case 集版本 / 两臂 commit / model revision / host / rubric 版本 / seed）
- **THEN** 校验失败并指出缺失字段；不执行任何案例

#### Scenario: 两臂 model revision 不一致时拒绝
- **WHEN** manifest 中两臂的 model/provider/revision 指纹不同
- **THEN** 校验失败（模型漂移是 #268 定义的硬失败）

### Requirement: 案例集必须覆盖四领域且不触碰 holdout

#### Scenario: 案例领域覆盖
- **WHEN** 检查 `evaluation/pilot/paired-pilot-v1.json` 的案例清单（8-12 个）
- **THEN** code / academic / business / ambiguous 四领域各 ≥2 个；每案例有 case_id、领域、任务描述、期望阶段证据类别

#### Scenario: holdout 隔离
- **WHEN** 任一案例与 #268 封存 holdout 集重叠
- **THEN** 该案例被移除并替换，替换记录于 manifest

### Requirement: 归因报告按四阶段双臂盲评且禁止综合分

#### Scenario: 报告结构
- **WHEN** `docs/evaluation/research/pilot-report-v1.md` 落盘
- **THEN** 含：per-stage（alignment/evidence/synthesis/delivery）双臂对比表、过程指标（方法多样性 / 溯源组数 / claim 准入结局 / 矛盾数 / 人工轮次）、阶段归因排序、以及显式的"不可下结论范围"声明；不含任何合成总分

#### Scenario: 模拟用户证据的边界
- **WHEN** 报告引用模拟用户交互数据
- **THEN** 该数据仅作为交互过程证据，不得表述为人类满意度结论

#### Scenario: host 不可用的降级交付
- **WHEN** 试点执行时真实 host 能力不可用
- **THEN** 交付 manifest + rubric + 执行说明并在报告头部声明 `not-run`（missing ≠ pass，#268 纪律）；不得以静态测试冒充试点执行

### Requirement: 试点输出必须驱动第二批排序

#### Scenario: 排序建议引用数据
- **WHEN** 第二批 alpha3 issue 排序建议被提出（Phase 4）
- **THEN** 建议逐条引用 pilot-report 的数据行；无法从数据支持的建议必须标注为"无证据，待第二批试点后复核"
