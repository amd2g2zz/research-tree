# T3 验收记录 (issue #576) — 2026-10-31

| 检查项 | 状态 | 证据 |
|---|---|---|
| #571 多项目隔离零串扰 | ✅ verified | 集成走查：双项目各自 vitals/默认投影互不串扰；归档删除规则（未归档拒绝、归档放行、隔离不破坏） |
| #572 全场跑重放确定性 | ✅ verified | 同拍重复 scrub 与新库 scrub 全等；全场 console 行数=拍数；verifyGraphChain 通过 |
| #573 四态归档含 REFRAMED 继承 | ✅ verified | GO→底稿、NO-GO→墓地、PARK→冻结简报、REFRAMED（显式提交 REFRAMED 裁决后）→fork 继承→chat；无复活条件的 NO-GO/PARK 双双拒绝（红线钉死）；墓地复活 revived_to+血缘边 |
| #574 fork 继承实测；主支默认投影；快照只读；H7 遥测 | ✅ verified | fork 快照+证据引用全等；分支尖端永不劫持默认投影；重复内容冻结拒绝+hash 不变；fork/version-continue 遥测事件落库 |
| ~~#575 外部 harness 实测~~ | ⊘ removed by ruling | 2026-10-30 pi-only 裁定移除；MCP 出口 #553 保留为产品接口（mcp_server.test + e2e 覆盖） |
| 验收记录落盘 | ✅ | 本文件 |

**结论**：T3 退出标准达成 → milestone #8 关闭，T4（#577 trigger-driven umbrella）开启。

**失败信号**：隔离断言变红（跨项目可见性）；复活条件红线被绕过；重放不确定（同拍不同投影）；已提交 hash 变化。
