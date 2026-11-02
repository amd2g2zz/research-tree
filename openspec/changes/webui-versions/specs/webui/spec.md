## ADDED Requirements

### Requirement: version timeline renders with fork markers and the draft row

版本页 SHALL 倒序渲染 vN/hash/裁决/摘要、⑂ 已分叉标记（分叉双端可见）、草稿行（未冻结·不可跟踪，冻结后消失）；主支/支线 SHALL 可辨（支线显示 fork 来源）。

#### Scenario: timeline with fork and draft
- **WHEN** a main line commits v0, forks from v0, and holds a draft
- **THEN** v0 shows ⑂ 已分叉, the fork side shows its fork parent, and the draft row is present until frozen

### Requirement: version actions with H7 telemetry and inherited forks

继续研究 SHALL 打开自最新提交复制的写时复制草稿（活动草稿优先恢复）；从此分叉 SHALL 生成继承快照的新任务并落 chat；两个动作 SHALL 落 H7 遥测（version-continue/fork）。

#### Scenario: fork inherits over the wire
- **WHEN** version.fork runs from v0
- **THEN** the new task is at chat phase with the inherited snapshot and a fork telemetry event lands

### Requirement: the snapshot view is read-only with a frozen banner

快照视图 SHALL 显示冻结横幅（vN·hash·裁决——不可再修改；继续研究=版本+1）与完整报告投影；未知版本 SHALL typed 404；四态归档 SHALL 可浏览。

#### Scenario: frozen banner and typed 404
- **WHEN** snapshot/0 and snapshot/9 are fetched
- **THEN** the former returns banner+report, the latter 404s with the engine's message
