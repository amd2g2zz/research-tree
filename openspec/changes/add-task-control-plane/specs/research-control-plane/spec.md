## ADDED Requirements

### Requirement: per-task stop state machine is one-way, idempotent, and persisted

每个调研任务 SHALL 有持久化控制状态 `running → stopping → stopped`（ledger migration v11 `task_control` 表）；转换 SHALL 单向（不可逆、不可跳过——markStopped 仅自 stopping 合法）；重复 stop SHALL 幂等（状态不变、不产生副作用）；无行的任务 SHALL 视为 running（存量兼容）。

#### Scenario: stop request persists running to stopping

- **WHEN** `research.stop` 对一个 running 任务发出
- **THEN** task_control 表出现 status='stopping' 的行（含 stop_requested_at），重复调用返回相同状态且不新增行

#### Scenario: repeated stop is idempotent

- **WHEN** stop 已处于 stopping/stopped 后再次调用 `research.stop`
- **THEN** 状态保持不变、阶段翻转与广播不重复发生

#### Scenario: stopped survives restart

- **WHEN** 服务进程在任务 stopped 后重启，新的控制面对同一 ledger 初始化
- **THEN** 该任务的 hydrate 状态为 stopped，且派发守卫继续拒绝其全部工作

### Requirement: dispatch boundary refuses stopped tasks at every entry

runner 的每个派发/完成边界 SHALL 检查任务控制状态：pumpOnce 派发与滚动派发 SHALL 跳过 stopping/stopped 任务；execute 入口与 completeStage 前的检查点 SHALL 拒绝（迟到完成被拒，产出不落账）；requeueOrphans SHALL 取消而非重排；arbiterWave SHALL 不为 stopped 任务生长新节点；closeGraphIfComplete SHALL 忽略非 running 任务。

#### Scenario: late completion rejected after stop

- **WHEN** 检索在飞期间 stop 发出，随后 provider 返回结果
- **THEN** execute 的 completeStage 前检查点拒绝完成：stage 落 `cancelled`，outputs 保持空，不发生综合调用

#### Scenario: arbiter wave skips a stopped task

- **WHEN** 图未完成且任务已 stopped
- **THEN** arbiterWave 不为该任务调用仲裁、不注册新节点

#### Scenario: orphan of a stopped task is cancelled, not retried

- **WHEN** stopped 任务存在 in_progress 孤儿阶段（重启残留）
- **THEN** requeueOrphans 将其置为 cancelled 终态而不是 failStage 重排

### Requirement: stage gains a cancelled terminal state

parallel_stages 状态枚举 SHALL 增加终态 `cancelled`：tick 永不派发 cancelled；stop 请求 SHALL 立即把该任务 pending 阶段翻转为 cancelled；cancelled 阶段 SHALL NOT 被重试或复活。

#### Scenario: pending stages land cancelled on stop

- **WHEN** stop 对有 pending 阶段的任务发出
- **THEN** 这些阶段立即变为 cancelled，tick 对它们返回零派发

### Requirement: dispatch isolation between tasks

派发决策 SHALL 按任务过滤（parallel_dag tick 支持排除任务集）：停止任务 A SHALL NOT 影响 任务 B 的派发、完成、闭合与生长。

#### Scenario: concurrent task keeps running while another stops

- **WHEN** 任务 A 在检索中收到 stop，任务 B 正常派发
- **THEN** B 的阶段在同泵内完成落账，A 的阶段被取消

### Requirement: in-flight work is cancelled where supported and reported honestly

pi 综合调用 SHALL 可取消（SIGTERM → 宽限 → SIGKILL，拒绝消息显式 cancelled）；注入式 runner 走同一取消注册路径；不可取消的调用（检索 provider）SHALL 在 stop 时如实广播上报"不可取消、结果将被丢弃"，且其迟到结果 SHALL 被丢弃。

#### Scenario: in-flight pi call is cancelled on stop

- **WHEN** 综合调用在飞（阻塞 runner）且 stop 发出
- **THEN** 取消句柄触发，调用以显式 cancelled 错误拒绝，不发生综合落账

#### Scenario: non-cancellable recon is reported honestly

- **WHEN** 检索在飞（阻塞 provider）且 stop 发出
- **THEN** 广播行如实说明该调用不可取消且结果将被丢弃，控制状态保持 stopping 直至调用排干

### Requirement: stopping drains to stopped only when in-flight work is gone

stopping 状态 SHALL 保持到该任务全部 in-flight 工作排干（可取消的取消、不可取消的返回并丢弃），随后 SHALL 落到 stopped 并持久化。

#### Scenario: stopping persists until the blocked call returns, then lands stopped

- **WHEN** 阻塞 provider 在飞时 stop 发出，随后 provider 释放
- **THEN** 排干检查将任务落到 stopped 并持久化（重启后仍为 stopped）

### Requirement: a stopped task cannot be resumed by re-registration or mode switch

对 stopping/stopped 任务，`research.start` 与 `mindmap.confirm` SHALL fail-closed 拒绝；重新注册阶段/切换研究模式 SHALL NOT 复燃 stopped 任务。

#### Scenario: mode switch does not resume a stopped task

- **WHEN** 对 stopped 任务调用 `research.start`
- **THEN** RPC 抛错拒绝，stage 表无新派发，控制状态保持 stopped

### Requirement: control status is visible over RPC and UI

`task.status` 与研究视图 SHALL 携带控制状态（running/stopping/stopped + stop_reason）；画布工具栏 SHALL 提供 Stop 按钮（running 可见），状态显示 SHALL 在刷新/重连后保持。

#### Scenario: stop status visible after refresh

- **WHEN** stop 落 stopped 后客户端刷新并重新拉取任务状态
- **THEN** RPC 返回 control.status='stopped'，UI 渲染停止态
