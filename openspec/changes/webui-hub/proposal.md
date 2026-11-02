# webui-hub

## Why

Issue #634 (WebUI wave row 3, docs 03 P2): 对话是项目主界面（hub）——研究从对话发起、结束后自动回对话。消息流（用户/rt 路由回执/系统事件）、任务状态卡（下一步动作唯一化）、追加信息门贯穿所有阶段、「聊得差不多了→分解」≥3 句门。消费 #555 DialogueController。

## What changes

- migration v8：`chat_messages`（task_id+seq 主键；role user/rt/system；receipt_json——hub 转写持久化）。
- webui-server：RPC `chat.send`（原 chat.ingest 扩展：落转写+回执，返回 routed_count）、`chat.history`、`task.status`（phase + latest + routed_count；freezeTask 语义=committed→chat 落地，正是"状态卡提交后消失"的引擎依据）。
- webui：P2 对话页——消息流（用户/rt 回执带四分路由标签）、状态卡（运行中/已提交两态）、输入框+语义分类选择器（**披露：LLM 自动分类随 keyed-session #588 接入，当前显式选择**）、分解按钮（routed_count≥3 可用，P3 页 #635）。

## impact_scope

- `rt-core/src/store/ledger.ts` (migration v8 append — MIGRATIONS registry, no external refs, text-confirmed)
- `webui-server/src/server.ts`, `webui-server/test/server.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
