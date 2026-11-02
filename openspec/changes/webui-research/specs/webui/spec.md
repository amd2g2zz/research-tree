## ADDED Requirements

### Requirement: the research page renders the trust face from engine state

研究页 SHALL 从引擎状态渲染三层图谱：研究问题 → 主线任务 → 阶段容器×主张行（后验/verify_tier/已决徽章）；主张后验 SHALL 以 claims surface 为权威（双写语义）。

#### Scenario: live view after a walk
- **WHEN** /api/research/:id is fetched after a launch with hub claims and a registered stage
- **THEN** claims (surface posteriors), stage containers, and transitions all render

### Requirement: scrubber replay is deterministic over the wire

重放条 SHALL 拖动到任意拍并同步图谱与 console；projection(t) SHALL 确定（同拍两次请求全等）且 SHALL 与拍数一致（t=全场时 console 行数=拍数）。

#### Scenario: same beat identical, full beat complete
- **WHEN** the same beat is fetched twice and then the final beat
- **THEN** the two mid-beat bodies are equal and the final console length equals the beat count

### Requirement: lineage drawer with no fake paths

主张点击 SHALL 打开抽屉显示 #566 三层 lineage（canvas-node→detail-drawer→raw-evidence ≤3 点击）；无 lineage 的主张 SHALL 如实显示"无 lineage"，SHALL NOT 伪造路径。

#### Scenario: committed claim resolves, ghost returns honest absence
- **WHEN** lineage is requested for a claim in a committed snapshot vs an unknown id
- **THEN** the former returns the three layers with raw evidence and the latter returns the no-fake-lineage error
