# pi-nt-latency

## Why

Issue #672（用户实测『消息发不出来』残余）：默认 5 扩展加载后，server 端结构化 pi 调用（分类）60s+、偶发 >120s 被 #670 超时 SIGTERM（用户看到发不出）。实测 \`-nt\`（禁用工具面——server 端调用只要文本 JSON）→ **18s**，3 倍提速。

## What changes

- runPi 增 extraArgs（默认 []，通用）；server 三条路径（chat.turn 回应/分类/decompose.fromChat 提取）与 classify 默认 runner 显式传 \`["-nt"]\`。
- 分类超时 120s→300s（对齐其它调用）。
- 超时错误信息区分信号杀死（"extensions may still be loading or the network is slow; retry"）。

## impact_scope

- \`webui-server/src/pi-run.ts\`, \`webui-server/src/classify.ts\`, \`webui-server/src/server.ts\`
