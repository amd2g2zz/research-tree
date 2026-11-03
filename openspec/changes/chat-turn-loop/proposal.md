# chat-turn-loop

## Why

Issue #660 (WebUI v3 三步流第 1 步，epic #659，docs/product/05 §1)：现状用户对着一堵墙——A1 策略引擎内置但 agent 不说话。chat.turn 让 agent **回应+主动提问+前期侦查**：每条话术获得实质回应（复述理解/指出缺口/下一步），歧视性提问消除歧义，侦查经 DataSourceProvider 端口真实执行并回填对话。

## What changes

- `chat-turn.ts`：buildTurnPrompt（转写+rt 对齐策略→结构化 prompt）、parseTurnOutput（严格 JSON {reply,questions[],recon?}；**reply 空=拒绝**——那正是要拆的墙）、runRecon/reconToText（provider 端口真实搜索）。
- server RPC `chat.turn`：keyed fail-closed；用户消息先落盘（分类并行 #651）→ pi 会话 → reply/questions 存 chat_messages（kind=reply/question）→ recon 经 provider 执行（provider.action 审计）→ recon 摘要存 kind=recon。provider 可注入（默认 anysearch）。
- 前端：agent 回应独立样式（rt 标签+实质正文）；主动提问渲染为问题卡（点击填入输入框）；recon 折叠详情；composer 自动档=对话回路、显式档=轻量路由；thinking 状态。

## impact_scope

- `webui-server/src/chat-turn.ts` (new), `webui-server/src/server.ts`, `webui-server/test/chat_turn.test.ts` (new)
- `webui/src/App.tsx`, `webui/src/styles.css`
