## ADDED Requirements

### Requirement: agent replies render as plain text in the chat column

agent 回应 SHALL 渲染为左对齐纯文本（无气泡底/边框），宽度随对话列且 SHALL NOT 挤压侧栏；用户消息保持右对齐彩色气泡。

#### Scenario: plain-text agent reply
- **WHEN** a turn reply renders
- **THEN** it is plain left-aligned text within the column and the sidebar is unaffected

### Requirement: questions are asked only on real gaps

turn prompt SHALL 指示模型仅在关键缺口存在时提 0-3 个问题（否则空数组）——SHALL NOT 每轮强制提问。

#### Scenario: prompt demands gap-driven questions only
- **WHEN** the turn prompt is built
- **THEN** it contains the gap-only questioning rule and empty questions arrays are valid

### Requirement: the decompose panel is removed; confirmation stage moves to a separate canvas (#661)

分解面板（按钮/状态/函数/动作卡跳转）SHALL 全部移除；确认阶段 SHALL 由 #661 思维导图 canvas 承接（converged 信号保留在 turn 结果中）。

#### Scenario: no decompose UI remains
- **WHEN** the app renders
- **THEN** no decompose panel/button/state references exist in the frontend bundle source
