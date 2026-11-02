# webui-closeout

## Why

Issue #639 (WebUI exit): P0-P5 全页面走查 + 红线清单 + 验收记录。走查形态：**wire-level e2e**——浏览器发起的 WS/REST 流量全集（与前端 build 验证共同构成页面证据），对真实账本 + 真实 pi 配置目录，LLM 留在 pi 边界（#607 先例 mock，接线本身真实）。

## What changes

- `webui-server/test/closeout.test.ts`: 五段走查——P0/P1（双项目隔离+删除红线+树）、P2（四分路由回执+≥3 门+转写回放）、P3（草稿→checklist 门→确认冻结→走查落 v0 GO）、P4（研究视图+确定性 scrubber+诚实 lineage）、P5（快照只读+fork 继承+H7 遥测+设置写 pi 同源+审计无名值+归档浏览）。
- 验收记录 evidence/acceptance.md。

## impact_scope

- `webui-server/test/closeout.test.ts` (new)
- `openspec/changes/webui-closeout/**` (new)
