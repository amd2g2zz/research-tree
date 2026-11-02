# webui-decomp

## Why

Issue #635 (WebUI wave row 4, docs 03 分解可视化 + docs 01 A0): 分解页六格卡墙——溯源律可见（每卡带"来自你的话/附件"引文）、编辑权在确认前（真删除按钮）、充分性 checklist（六类各 ≥1，拒绝点显式为无；缺口阻止确认）、确认后冻结为研究宪法（变更=重大转向重签）。消费 #598 分解引擎。

## What changes

- webui-server RPC：`decompose.prepare`（LLM extraction → parseDecomposition 溯源过滤 → saveDraftDecomposition 草稿+checklist；**不确认**）、`decompose.get`、`decompose.removeElement`（确认前重起草；**已确认拒绝=major pivot verbatim**）、`decompose.confirm`（checklist 门 → confirmDecomposition + attachDecomposition）、`decompose.checklist`。
- rt-core `headless/runner.ts`：attach 步幂等——同一已确认分解的重复 attach 为 no-op（P3 先确认再走查是合法路径；其它确认错误仍 fail-closed）。rt-core 334/334 不变。
- webui：P3 六格卡墙（🎯📌📖💡🚫⚠ + 溯源引文 + 逐卡删除 + checklist 横幅绿/黄 + 确认按钮被缺口禁用 + "待对齐"占位如实呈现）。

## impact_scope

- `rt-core/src/headless/runner.ts` (attach idempotence)
- `webui-server/src/server.ts`, `webui-server/test/decompose.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
