## ADDED Requirements

### Requirement: one pi call per turn with instant user echo

chat.turn SHALL 在**单次** pi 调用中同时产出 kind 与 reply（不串行分类）；用户气泡 SHALL 在发送后即时渲染（乐观更新，失败回滚），等待期 SHALL 显示 typing 指示。

#### Scenario: single call, kind judged in the same output
- **WHEN** chat.turn runs
- **THEN** exactly one user row, one reply row and N question rows land (no duplicates) and the result carries kind + classified_by=pi-session

#### Scenario: kind required
- **WHEN** the model output lacks a valid kind
- **THEN** the turn throws naming the unusable kind

### Requirement: ChatGPT-style bubble semantics

用户消息 SHALL 渲染为右对齐彩色气泡，agent 回应 SHALL 为左对齐独立底色——一左一右、颜色分明（状态仍不裸靠颜色）。

#### Scenario: layout
- **WHEN** a conversation renders
- **THEN** user bubbles align right with their background and agent responses align left with a distinct panel background
