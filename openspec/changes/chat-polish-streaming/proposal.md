# chat-polish-streaming

## Why

Issue #679（用户 5 条反馈）：①分解顶栏按钮多余——确认应由对话语义驱动；②侧栏折叠按钮乱跳；③chat 未按语义进入思维导图确认；④消息垂直间距挤；⑤**chat 非流式**——应思维链先流式、完成后自动折叠、正文随后；侦查引用 1、2、3… 编号带链接。

## What changes

- runPi 增 onDelta（stdout 增量钩子）；chat.turn 广播 {event:turn-start/turn-delta} 到所有 WS 客户端。
- turn JSON 增 **converged**（模型判定想法是否成形）；converged=true 且 routed_count≥3 时流内出现「进入思维导图确认 →」动作卡（打开确认面板；树形独立页 #661）。
- 顶栏移除「分解」按钮（语义入口在流内）。
- 侧栏折叠按钮固定在顶栏左侧单一位置。
- 间距：用户/agent 消息 18px 垂直间距。
- 侦查引用结构化落库（results:[{n,title,url,snippet]}）+ reconToText 编号化；前端编号渲染。
- 前端思维链：流式 pre 块（thinkingText ref 累积，闭包安全），完成后自动折叠为「思维链（已完成）」details。

## impact_scope

- `webui-server/src/pi-run.ts`, `webui-server/src/chat-turn.ts`, `webui-server/src/server.ts`
- tests: `webui-server/test/chat_turn.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
