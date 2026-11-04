# chat-plain-ux

## Why

Issue #681（用户 3 条反馈）：①agent 回应气泡太宽挤到侧栏——ChatGPT 式改纯文本；②回复不停提问——提问与 ask 工具同策略，仅真实缺口才问；③分解不需要了，确认阶段走单独 canvas（#661）。
另发现：pi 可执行文件在 /private/tmp scratch 被清理导致 server 全部 pi 调用 fail-closed（消息发不出的当前根因）——pi 永久安装到 ~/.pi/agent/npm 并加入 resolvePiCommand 搜索链。

## What changes

- 前端：移除分解面板/函数/状态/动作卡跳转（确认阶段 canvas=#661）；agent 回应改纯文本（无气泡底/边框，宽度随对话列）；提问策略 prompt 改「仅关键缺口 0-3 个，否则空数组——不为问而问」。
- server resolvePiCommand：RT_PI_CMD → PATH → **~/.pi/agent/npm 持久安装** → scratch（原顺序保留）。
- pi 本体永久安装（npm @mariozechner/pi-coding-agent 至 ~/.pi/agent/npm）。

## impact_scope

- `webui-server/src/chat-turn.ts`, `webui-server/src/server.ts`
- tests: `webui-server/test/chat_turn.test.ts`
- `webui/src/App.tsx`
