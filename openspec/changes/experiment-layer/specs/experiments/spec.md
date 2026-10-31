## ADDED Requirements

### Requirement: pre-registration precedes execution

实验 SHALL 先注册后执行：注册时校验预注册字段并落盘为 registered，只有 execute 能转为 running。

#### Scenario: register then execute
- **WHEN** an experiment is registered with hypothesis/criterion/min_sample/cost_cap/designer
- **THEN** the row persists with status `registered`, and only `execute` moves it to `running`

#### Scenario: prereg fields validated
- **WHEN** hypothesis or criterion is empty, min_sample < 1, or cost_cap <= 0
- **THEN** register throws

### Requirement: designer never executes (anti-rigging)

设计者 SHALL 不执行：executor 与预注册 designer 同一身份时拒绝执行，防 rigged 实验。

#### Scenario: same identity rejected
- **WHEN** execute is called with executor identical to the preregistered designer
- **THEN** a LedgerIntegrityError mentioning the designer rule is thrown

### Requirement: sequential stop (SPRT-style)

序贯停止 SHALL 生效：观测推进后验越过阈值且达到最小样本量即停，不足最小样本量继续。

#### Scenario: posterior past threshold
- **WHEN** a recorded observation pushes the posterior to ≥ 0.95 with sample ≥ min_sample
- **THEN** the experiment stops with reason `posterior-past-threshold`

#### Scenario: below min sample keeps running
- **WHEN** posterior ≥ 0.95 but sample < min_sample
- **THEN** the experiment keeps running

### Requirement: budget ladder hard gate

阶梯硬门 SHALL 生效：预估成本超过预注册 cost_cap 的实验标记 experiment-gated 进风险登记，不跑。

#### Scenario: over-cap cost is experiment-gated, not run
- **WHEN** estimated_cost exceeds the preregistered cost_cap
- **THEN** checkBudget returns `experiment_gated: true` and the experiment is not executed
