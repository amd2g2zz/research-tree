# add-task-control-plane — tasks

- [x] 1. migration v11 `task_control` 表 + TaskControlPlane 状态机（单向/幂等/hydrate）+ rt-core 测试
- [x] 2. parallel_dag：tick 排除过滤 + `cancelled` 终态 + cancelStage + rt-core 测试
- [x] 3. WS-F fixtures：脚本化 fake pi runner + 可阻塞 provider（webui-server/test/fixtures/）
- [x] 4. pi-run：runPiCancellable（SIGTERM→宽限→SIGKILL，显式 cancelled 拒绝）+ 测试
- [x] 5. runner 守卫：派发边界检查点 + 取消注册 + 逐任务分组（pump/arbiter/close/requeue）+ TDD 矩阵
- [x] 6. server：`research.stop` RPC + control 状态透出（task.status/researchView）+ research.start/mindmap.confirm 拒绝 + 测试
- [x] 7. UI：画布工具栏 Stop 按钮 + running→stopping→stopped 状态显示（刷新保持）
- [ ] 8. 全部本地门 + PR（Closes #742）
