# chat-send-ux

## Why

Issue #674（用户反馈 2026-11-03）：消息发不出来 + 排列不像 ChatGPT。三个真问题：①用户消息不即时上屏（等整个回合 60-120s 后才刷新）；②一次消息跑两次串行 pi（分类+回应）；③agent 回应无独立气泡语义。

## What changes

- **单次 pi 调用**：turn prompt 合并分类（输出 {kind, reply, questions, recon}；kind 非法 fail-closed）；chat.turn 落库去重（user/reply/question 各一次，classified_by=pi-session）。
- **前端即时回显**：发送后 user 气泡立即渲染（乐观更新，失败回滚到服务器真相）；thinking 时 agent 侧三点脉冲指示。
- **气泡语义**（ChatGPT 式）：用户=右对齐蓝色底气泡；agent=左对齐浅灰底带边框；一左一右颜色分明。

## impact_scope

- `webui-server/src/chat-turn.ts`, `webui-server/src/server.ts`
- tests: `webui-server/test/chat_turn.test.ts`, `webui-server/test/pi_run.test.ts`, `webui-server/test/recon_degrade.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
