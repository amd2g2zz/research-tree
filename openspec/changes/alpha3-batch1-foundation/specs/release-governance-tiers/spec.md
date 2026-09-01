## ADDED Requirements

### Requirement: 发布治理声明必须四档化

发布能力声明必须区分四档：`published`（包发布）/ `alpha-pilot-suitable`（Alpha 试点适用）/ `org-rollout-ready`（组织推广就绪）/ `unattended-final-authority`（无人值守最终权威）。治理文档不得使用跨档的绝对化表述。

#### Scenario: 绝对化表述消除
- **WHEN** 扫描 `docs/governance/*`
- **THEN** 不存在"open benchmark issue → 不能发布"类把单一 open 评测 issue 当作包发布硬阻断的表述；每处发布约束都归属于明确的一档

#### Scenario: 已发布 Alpha 的证据债表述
- **WHEN** 描述已发布版本（如 0.1.0-alpha2）与 open 评测 issue 的关系
- **THEN** 表述为"该 issue 是某档声明的证据债/限制"，并指向该档的回退触发与后续度量，而非"不应存在"

### Requirement: 每个 open 评测 issue 必须声明 gate 边界

#### Scenario: per-issue gate 声明存在
- **WHEN** 治理文档列举 open 评测 issue（如 #67 #84 #292 #323）
- **THEN** 每个 issue 附一行声明格式 `gates <档>; does not gate <档>`，且该声明可被 `check_docs.py` 机器校验

#### Scenario: 外部依赖工作不得成为无限代码发布阻断
- **WHEN** 某评测 issue 依赖外部资源（评审人/资金/holdout）
- **THEN** 治理文档声明其为对应档的限制条件与降级路径，而非阻塞 `published` 档
