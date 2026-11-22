# add-task-control-plane

## Why

Issue #742（P0）：调研画布没有停止控制。`BackgroundResearchRunner.stop()` 只 `clearInterval`（research_worker.ts:124-129）——用户离开后后台 runner 继续派发；进行中的 pi/检索调用无法取消；freeze 判决不是停止动作。根因是运行时没有**任务级控制面**：停止语义既不按 taskId 生效，也不持久化。

## What changes

- **migration v11**：ledger 新表 `task_control(task_id, status, stop_reason, stop_requested_at, updated_at)`，状态机 `running→stopping→stopped` 单向（machine.ts 转换矩阵模式）。
- **TaskControlPlane（rt-core/src/state/task_control.ts）**：显式转换矩阵 + 幂等 requestStop + markStopped + 构造时 hydrate（内存权威映射 + 表持久化双写）；无行 ≡ running（存量任务兼容）。
- **`research.stop` RPC**（server.ts 新 case，switch 模式）：按 taskId 持久化 stopping → 触发 runner 立即取消（不等 5s 泵）→ 返回状态。`task.status` / research 视图携带 control 状态（刷新/重启后保持）。
- **派发边界守卫**：pumpOnce 派发/滚动派发、execute 入口与 completeStage 前检查点、requeueOrphans、arbiterWave、closeGraphIfComplete 一律按控制状态过滤——stopped/stopping 任务零新派发、零重试、零生长；`parallel_dag.ts` tick() 增排除过滤（修 :88 全表跨任务耦合的机械前提）、增 `cancelled` 终态与 cancelStage()。
- **pi 取消**：runPi 拆出 runPiCancellable（SIGTERM→宽限→SIGKILL，拒绝消息显式 "cancelled"）；注入式 runner 经可取消包装走同一路径；不可取消的调用（recon provider 检索）**如实广播上报**并丢弃迟到结果。
- **重启 hydrate**：进程重启后 plane 从 task_control 表恢复；stopped 任务 research.start/mindmap.confirm 拒绝（模式切换不复燃）；其它任务不受任何影响。
- **UI**：画布工具栏 Stop 按钮（running 可见）+ running→stopping→stopped 状态显示，刷新后保持。
- **WS-F fixture 基建**：`webui-server/test/fixtures/`——脚本化 fake pi runner（正常/阻塞/慢/取消）+ 可阻塞 fake provider（本 PR 与 #744 复用）。

## impact_scope

- `rt-core/src/store/ledger.ts`（migration v11）
- `rt-core/src/state/task_control.ts` (new)
- `rt-core/src/scheduler/parallel_dag.ts`（tick 排除过滤 + cancelled 终态）
- `webui-server/src/research_worker.ts`（守卫 + 取消注册 + 逐任务分组）
- `webui-server/src/pi-run.ts`（runPiCancellable）
- `webui-server/src/server.ts`（research.stop case + control 状态透出）
- `webui/src/views/ResearchPage.tsx`（Stop 按钮 + 状态）
- tests: `webui-server/test/fixtures/` (new), `webui-server/test/task_stop.test.ts` (new), `webui-server/test/pi_run.test.ts`（取消用例）, `rt-core/test/task_control.test.ts` (new), `rt-core/test/parallel_dag.test.ts`（排除/取消用例）

## Non-goals

- 预算/usage 仪表盘（#743 下一波，migration v12）
- 后台并发架构重写（maxConcurrent 语义保持）
- 模式策略（#747）
