# keyed-session

## Why

Issue #651: 设置页（#638）已可配 key；本 issue 落地 keyed-session **就绪探针** + hub 话语**自动分类**。LLM 产生判断（分类），判断落盘为数据后由算法统治——四分路由仍是 #555 机械规则，路由/回执/账本不变。

## What changes

- `classify.ts`：ClassificationPort 策略注册表——**PiSessionClassifier**（spawn pi headless，结构化 prompt→严格 JSON 解析；runner 可注入，CI 永不 spawn 真 pi）+ **HeuristicClassifier**（确定性关键词回退，如实披露为规则而非 LLM）；`pickClassifier` 按就绪度选择。
- pi-config：`keyed_session_ready`（auth.json 有 provider key ∧ 有默认模型）+ readiness 明细；/api/config/pi 带就绪字段。
- server chat.ingest：kind 可选——显式 kind 永远被尊重（classified_by=user）；缺省走端口（keyed→pi-session，否则 heuristic 回退）；转写与回执带 classified_by（**不假装自动**）；分类失败 fail-closed（unusable kind/malformed JSON 抛错，不猜）。
- webui：kind 选择器新增「自动分类」档（默认），发送后披露服务的分类器（手动/pi 会话自动/规则回退）。

## impact_scope

- `webui-server/src/classify.ts` (new), `webui-server/src/pi-config.ts`, `webui-server/src/server.ts`
- tests: `webui-server/test/keyed_session.test.ts`, `webui-server/test/server.test.ts` (nonsense-kind now auto-classifies by design)
- `webui/src/App.tsx`
