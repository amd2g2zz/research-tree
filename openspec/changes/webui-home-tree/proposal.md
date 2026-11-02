# webui-home-tree

## Why

Issue #633 (WebUI wave row 2, docs 03 P0/P1): 项目首页=应用默认落点（卡片墙：建/列/归档/删——仅归档可删，引擎红线原样上抛）；侧栏研究树=唯一导航器（项目→任务→版本/草稿三层，⑂ 分叉标记，草稿行"未冻结·不可跟踪"）。消费 #571 ProjectHomeModel 与 #548 版本存储。

## What changes

- webui-server：`GET /api/tree`（树形装配：projects → lines(main/fork) → versions 倒序（vN/hash/裁决/⑂forked）+ draft 行 + vitals）；RPC `project.archive` / `project.delete`（引擎红线 verbatim：未归档删除拒绝、归档只读）。
- webui：P1 侧栏树组件（三层可点、状态徽章、fork 标记、草稿金棕色标注）；P0 卡片墙升级（附件 chips、归档/删除按钮、首次提交后"查看最新报告"入口位）；logo 点击回首页。

## impact_scope

- `webui-server/src/server.ts` (tree + archive/delete RPC)
- `webui-server/test/server.test.ts` (tree payload + management red lines)
- `webui/src/App.tsx`, `webui/src/styles.css`
