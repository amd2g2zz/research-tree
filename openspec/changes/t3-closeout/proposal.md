# t3-closeout

## Why

Issue #576 (T3 exit): 多项目隔离 + 四态归档 + 回放确定性——一个集成账本内跨 #571/#572/#573/#574 全部 T3 机械规则。（#575 外部 harness 实测已按 2026-10-30 pi-only 裁定移除；MCP 出口 #553 保留为产品接口，由 mcp/e2e 套件覆盖。）

## What changes

- `test/t3_closeout.test.ts`: 集成走查——双项目隔离（vitals/默认投影互不串扰）、四态归档（PARK/NO-GO 复活条件红线钉死、REFRAMED 提交裁决后继承账本、墓地复活 revived_to+血缘）、fork 继承实测（快照+证据全等）、快照只读（重复内容冻结拒绝、hash 不变）、H7 遥测、全场跑确定性重放（重复/新库 scrub 全等 + 链校验）；删除规则（未归档拒绝/归档放行/隔离不破坏）。
- 附带：ProjectHomeModel.defaultProjection 返回 task_id（投影点名其任务）。

## impact_scope

- `rt-core/src/ux/project_home.ts` (defaultProjection +task_id)
- tests: `rt-core/test/t3_closeout.test.ts`
