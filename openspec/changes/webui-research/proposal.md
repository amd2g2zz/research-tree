# webui-research

## Why

Issue #636 (WebUI wave row 5, docs 03 P4): 研究页=信任面——三层图谱（❓研究问题→🧵主线任务→调研 DAG 阶段容器×主张行）、console 同步重放（#572 scrubber 接上拖动条）、主张抽屉（#566 lineage ≤3 点击）。图例/缩放/minimap 按克制清单后置。

## What changes

- webui-server：`GET /api/research/:taskId`（#559 CanvasProjection + claims surface 权威后验合并 + parallel_stages 阶段容器）、`/beats`（#572 全场拍列表+摘要）、`/at/:t`（事件前缀纯投影：console 行+当时快照）、`/lineage/:v/:claimId`（#566 三层下钻；未知主张 no-fake-lineage）。
- webui P4 研究页：图谱面板（问题/任务/阶段容器+主张行带后验/tier/已决徽章+孤儿主张行）、重放条（拖动→projection(t)，console 与图谱同步）、主张抽屉（lineage 三层+原始证据+关闭）。

## impact_scope

- `webui-server/src/server.ts`, `webui-server/test/research.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
