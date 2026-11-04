# full-canvas-restructure

## Why

Issue #683（用户裁定：三步流必须是三个独立全屏页面，非面板）：chat hub → 全画布思维导图确认 → 全画布调研 DAG。

## What changes

- migration v9：`mindmaps` 表（task_id PK, tree_json, status draft|confirmed）。
- `mindmap.ts`：mindmapPrompt（转写→树 JSON≤5 级 quote 溯源）、parseMindmap（quote 回查+branch 身份标签）、mechanicalPlan（叶子→stages）、editNode（draft 增删改）。
- server RPC：mindmap.generate / get / editNode / confirm（确认→树→六要素分解→stages 注册→research 相位）。
- 前端：MindmapPage（全画布横向树+CSS 连接线+节点内联编辑+溯源引文+确认按钮）；ResearchPage（DAG 深度分列+阶段卡+状态徽章+Console 条+冻结裁决）；App.tsx view router（chat|mindmap|research 全屏切换）。

## impact_scope

- `rt-core/src/store/ledger.ts` (migration v9)
- `webui-server/src/mindmap.ts` (new), `webui-server/src/server.ts`
- tests: `webui-server/test/mindmap_rpc.test.ts` (new)
- `webui/src/App.tsx`, `webui/src/MindmapPage.tsx` (new), `webui/src/ResearchPage.tsx` (new), `webui/src/styles.css`
