## ADDED Requirements

### Requirement: the agent responds substantively to every utterance

每条用户话术 SHALL 获得实质回应（复述理解+指出缺口+下一步）——空 reply SHALL 被拒绝（fail-closed）；回应与主动提问 SHALL 落 chat_messages（kind=reply/question）成为转写数据；分类回执（#651）SHALL 并行保留不受影响。

#### Scenario: substantive reply stored
- **WHEN** chat.turn runs with an injected runner on a keyed server
- **THEN** the transcript gains kind=reply and kind=question rows and the classification receipt remains on the user message

#### Scenario: empty reply refused
- **WHEN** the model returns an empty reply
- **THEN** the turn throws naming the substantive-reply rule

### Requirement: early reconnaissance executes through the provider port

模型提议侦查（recon.query）时 SHALL 经 DataSourceProvider 端口真实执行（默认 anysearch，可注入），结果 SHALL 折叠回填对话（kind=recon）并落 provider.action 审计。

#### Scenario: recon executes and audits
- **WHEN** the turn output requests a recon query
- **THEN** the injected provider receives the query, the transcript gains a recon row, and one anysearch audit event lands

### Requirement: conversational turns fail closed without a keyed session

非 keyed 会话 SHALL 拒绝对话回路（指引设置页），SHALL NOT 提供模拟对话。

#### Scenario: unkeyed refuses
- **WHEN** chat.turn runs on a non-keyed server
- **THEN** it throws mentioning the keyed session requirement
