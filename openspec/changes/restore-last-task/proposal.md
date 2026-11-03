# restore-last-task

## Why

#653 follow-up（agent-browser e2e 复现的产品缺陷）：重开 app 默认选中**第一个**项目——资深用户的预期是恢复**自己上次的研究**（ChatGPT 恢复上次会话的同款行为）。这也是 e2e 误操作他项目的根因。

## What changes

- activeTaskId 恢复序：current → **localStorage rt-last-task**（且任务仍存在）→ 第一个 active 项目主线。
- 每次 activeTaskId 变化写入 localStorage。

## impact_scope

- `webui/src/App.tsx`
