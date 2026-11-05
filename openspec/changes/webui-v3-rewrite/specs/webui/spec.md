## ADDED Requirements

### Requirement: ChatGPT-style three-view layout

WebUI SHALL 以 ChatGPT 式布局呈现：侧栏项目列表 + 居中对话流 + 底部输入胶囊 + 顶栏视图切换按钮。用户气泡右对齐彩色，agent 回应左对齐纯文本，思维链流式渲染。

#### Scenario: chat renders with proper layout
- **WHEN** the app loads
- **THEN** the sidebar shows projects, the main area shows centered chat with the composer pill, and the view buttons are in the topbar
