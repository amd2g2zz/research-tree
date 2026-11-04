## ADDED Requirements

### Requirement: the chat streams 思维链 first, auto-collapses, then renders the reply

chat.turn SHALL 流式转发 pi stdout 增量到浏览器（turn-delta 事件）；前端 SHALL 流式渲染思维链块，回合完成 SHALL 自动折叠为可展开的「思维链（已完成）」并渲染正文。

#### Scenario: streaming then collapse
- **WHEN** a chat.turn runs
- **THEN** turn-delta events stream to the socket, the thinking block grows, and after the reply lands the thinking block renders collapsed

### Requirement: semantic entry into the confirmation stage

turn 输出 SHALL 含 converged（模型判定想法是否成形）；converged 且对话充分时流内 SHALL 出现「进入思维导图确认」动作卡；顶栏 SHALL NOT 常驻分解按钮。

#### Scenario: converged drives the action card
- **WHEN** a turn lands with converged=true after ≥3 routed sentences
- **THEN** the in-stream action card offers 进入思维导图确认 and the topbar has no 分解 button

### Requirement: numbered linked citations and stable layout

侦查结果 SHALL 按 1、2、3… 编号渲染且每条带链接（结构化落库）；侧栏折叠按钮 SHALL 固定单一定位；用户与 agent 消息 SHALL 有 ≥18px 垂直间距。

#### Scenario: numbered citations
- **WHEN** recon results land
- **THEN** the transcript stores structured {n,title,url,snippet} and the UI renders numbered linked entries
