## ADDED Requirements

### Requirement: version timeline with draft row and fork markers

版本页 SHALL 渲染倒序时间线（vN/hash/裁决/摘要）、fork 标记（⑂ 已分叉→支线），存在草稿时 SHALL 显示草稿行（未冻结·不可跟踪），冻结后 SHALL 消失。

#### Scenario: timeline newest-first with fork marker
- **WHEN** a task commits v0 and v1 and forks from v0
- **THEN** the timeline lists v1 then v0, marks v0 as forked, and shows 64-char hashes

### Requirement: main-branch default projection, switching explicit

主分支 SHALL = 无 fork parent 的任务；默认投影 SHALL 恒为主支最新版本——分支尖端 SHALL NOT 劫持默认视图，切换 SHALL 恒为显式 (task_id, v) 寻址。

#### Scenario: branch tip never hijacks the default
- **WHEN** a fork commits a newer version than the main line
- **THEN** defaultProjection still resolves to the main line's latest

### Requirement: version+1 and fork actions with H7 telemetry

继续研究 SHALL 打开自最新提交复制的写时复制草稿——活动草稿 SHALL 优先恢复且 SHALL NOT 被覆盖；从此分叉 SHALL 生成继承快照的新任务并落 chat；两个动作 SHALL 落 H7 遥测事件。

#### Scenario: live draft resumed, not clobbered
- **WHEN** continueResearch runs with a live draft present
- **THEN** the draft content is unchanged

#### Scenario: fork inherits
- **WHEN** fork runs from a committed version
- **THEN** the new task's v0 snapshot equals the source and a telemetry event lands

### Requirement: read-only snapshot view

快照视图 SHALL 只读：冻结横幅（vN·hash·裁决）+ 完整报告投影；已提交内容 SHALL 永不改变（重复内容冻结 SHALL 被拒绝，append-only）。

#### Scenario: committed content never mutates
- **WHEN** an identical snapshot re-freeze is attempted after opening a draft
- **THEN** it is rejected and the original commit hash is unchanged
