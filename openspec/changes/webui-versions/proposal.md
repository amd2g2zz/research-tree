# webui-versions

## Why

Issue #637 (WebUI wave row 6, docs 03 P5 + 快照视图): 版本时间线（vN/hash/裁决/摘要倒序 + 草稿行"未冻结·不可跟踪" + ⑂ 已分叉标记）、继续研究/从此分叉动作（H7 遥测）、只读快照视图（冻结横幅+完整报告+回当前工作区）、四态归档浏览。消费 #574 VersionTimeline + #573 FourStateArchive。

## What changes

- webui-server：`GET /api/versions/:taskId`（timeline）、`GET /api/versions/:taskId/snapshot/:v`（只读快照；404 typed）、`GET /api/archive`（四态+墓地）；RPC `version.continue`（version+1，活动草稿优先恢复）、`version.fork`（分叉即继承→chat）。
- webui P5：时间线（倒序+⑂ 标记+草稿行金棕）、动作按钮、快照模态（🔒冻结横幅"不可再修改；继续研究=版本+1"+报告投影+回当前工作区）、归档浏览。

## impact_scope

- `webui-server/src/server.ts`, `webui-server/test/versions_page.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
