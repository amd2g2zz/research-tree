## ADDED Requirements

### Requirement: reopening the app restores the user's last research

app 加载 SHALL 恢复用户上次激活的任务（localStorage 持久化，任务存在性校验），而非默认第一个项目。

#### Scenario: reopen restores last task
- **WHEN** the app reloads after working on task X
- **THEN** task X is re-selected (its transcript renders) rather than the first project in the tree
