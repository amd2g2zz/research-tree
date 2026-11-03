# async-pi-runner

## Why

Issue #670（用户实测：webui 一直卡着）：server 所有 pi 调用用 **spawnSync**——pi（DeepSeek+6 扩展）单次 45s+，Node 事件循环全程冻结，**所有** HTTP/WS 请求排在一次同步 spawn 后面，整站卡死；且无超时，pi 挂起则永久卡死。

## What changes

- `pi-run.ts`：runPi——async spawn（promise 包装）+ 硬超时（kill + typed PiRunError）+ 退出码进错误消息。
- classify.ts：classify 改 **async**（PiSessionClassifier 默认 runner 走 runPi+120s 超时；HeuristicClassifier 同签名 async；runner 类型放宽 string|Promise）。
- server：chat.turn / chat.ingest(keyed) / decompose.fromChat 全部 await runPi/await classify；piTimeoutMs 可配（turn/提取 300s、分类 120s）；piRunner 类型放宽 async。
- 事件循环证明：慢 runner（3s）在飞期间 REST 读 <1s 响应（旧实现冻结 3s+）。

## impact_scope

- `webui-server/src/pi-run.ts` (new), `webui-server/src/classify.ts`, `webui-server/src/server.ts`
- tests: `webui-server/test/pi_run.test.ts` (new), `webui-server/test/keyed_session.test.ts` (async)
