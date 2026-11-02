## ADDED Requirements

### Requirement: the hub transcript persists with routing receipts

对话转写 SHALL 持久化（migration v8）：每句用户话术与其 rt 四分路由回执 SHALL 成对落库并可经 chat.history 回放。

#### Scenario: history round-trips
- **WHEN** three utterances are sent and chat.history is read
- **THEN** six messages return (3×user+rt) and every rt row carries a parsed receipt

### Requirement: the task status card derives from engine state, next action unique

状态卡 SHALL 从引擎状态推导（phase + latest version）：未提交且 phase≠chat → 运行中；已提交 → 报告+版本+1 入口且**提交后消失**（freezeTask 落回 chat 正是其消失依据）；「聊得差不多了→分解」SHALL 在 ≥3 句被路由后才可用。

#### Scenario: status card across the walk
- **WHEN** a task walks chat→decompose→research→converged→committed
- **THEN** task.status reports phase back at chat with the committed latest (v0, verdict), and routed_count gates the decompose button

### Requirement: the append-info gate spans all phases

输入框 SHALL 贯穿所有阶段可用；语义分类 SHALL 如实披露当前为显式选择（LLM 分类器随 keyed-session provisioning 接入），SHALL NOT 假装自动。

#### Scenario: disclosed classification
- **WHEN** the chat panel renders
- **THEN** the kind selector is visible with the keyed-session disclosure note
