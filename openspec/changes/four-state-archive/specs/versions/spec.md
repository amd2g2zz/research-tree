## ADDED Requirements

### Requirement: all four verdicts archive with their disposition

四态 SHALL 按裁决归档：GO→底稿交接指针；NO-GO→墓地条目（原因+复活条件）；PARK→冻结简报+复活条件；REFRAMED→fork 继承账本（新任务 chat 起步、v0 继承快照）并带 delta 报告。四态 SHALL 可浏览。

#### Scenario: four states in one ledger
- **WHEN** one GO, one NO-GO, one PARK, one REFRAMED version are archived
- **THEN** list() returns all four with their disposition kinds

#### Scenario: REFRAMED inherits the ledger
- **WHEN** a REFRAMED version archives with new_task_id and delta_report
- **THEN** the new task exists at chat phase with an inherited v0 snapshot

### Requirement: revival conditions are mandatory for NO-GO and PARK (red line)

NO-GO 与 PARK 的归档 SHALL 携带非空复活条件——缺失 SHALL 被拒绝（钉死）；PARK 另 SHALL 要求冻结简报。

#### Scenario: missing revival conditions rejected
- **WHEN** a NO-GO or PARK version archives without revival conditions
- **THEN** an ArchiveError mentioning revival is thrown

### Requirement: graveyard revival forks with inheritance

复活 SHALL = 从墓地版本 fork：新任务 SHALL 继承快照（分叉即继承），血缘边 SHALL 可查，墓地条目 SHALL 记录 revived_to。

#### Scenario: revival inherits and records
- **WHEN** revive runs on a graveyard entry
- **THEN** the new task's v0 snapshot equals the source, the fork edge is queryable via forkChildren, and the entry records revived_to
