## ADDED Requirements

### Requirement: T2 exit walk over five real ideas

T2 退出 SHALL 在五个不同形态的真实想法上走查 T2 机械规则（早终止/H5、双席、并行 DAG、lineage、实验层），全部断言通过。

#### Scenario: five-idea walk is green
- **WHEN** the t2_closeout suite runs
- **THEN** all five ideas pass their capability assertions plus the #568/#569 cross-cutting invariants

### Requirement: over-budget experiments never execute

阶梯硬门 SHALL 拦截执行：checkBudget 判定 gated 的实验 SHALL 被 execute 拒绝（不只标记）。

#### Scenario: gated experiment execute rejected
- **WHEN** an experiment is gated by checkBudget and execute is called
- **THEN** a LedgerIntegrityError is thrown
