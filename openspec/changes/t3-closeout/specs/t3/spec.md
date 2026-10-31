## ADDED Requirements

### Requirement: T3 exit walk in one integrated ledger

T3 退出 SHALL 在单一集成账本内走查：多项目隔离、四态归档（含 REFRAMED 继承与红线拒绝）、fork 继承实测、快照只读、H7 遥测、全场跑确定性重放。

#### Scenario: integrated walk is green
- **WHEN** the t3_closeout suite runs
- **THEN** isolation, archival, inheritance, immutability, telemetry, and replay assertions all pass

### Requirement: project default projection names its task

项目默认投影 SHALL 携带 task_id——投影点名其来源任务。

#### Scenario: projection resolves per project
- **WHEN** two projects each hold commits and a fork
- **THEN** each defaultProjection names its own main task
