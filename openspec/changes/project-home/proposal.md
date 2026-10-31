# project-home

## Why

Issue #571 (T3 row 1, docs 03 P0): 项目首页是应用默认落点。三体征（研究线数/主分支最新版本+裁决+hash/主线已用时间）、研究线列表、卡片墙管理（建/列/归档/删）、主分支最新为默认投影（A7 规则 5）、多项目并行隔离零串扰。

## What changes

- migration v5：`projects`（name/description/status/attachments）+ `project_tasks`（task→project 归属, main|fork, main 唯一）。
- `ux/project_home.ts`: ProjectHomeModel — createProject / registerTask（归档项目只读、main 唯一）/ vitals / listLines / defaultProjection（主分支最新，fork 提交永不劫持首页）/ hasLatestReport（首次提交后自动长出"查看最新报告"）/ archive / delete（**仅归档可删**）。
- 所有查询按 project_id 作用域化——多项目并行零串扰。

## impact_scope

- `rt-core/src/store/ledger.ts` (migration v5 append — MIGRATIONS registry, no external refs, text-confirmed)
- `rt-core/src/ux/project_home.ts` (new)
- tests: `rt-core/test/project_home.test.ts`
