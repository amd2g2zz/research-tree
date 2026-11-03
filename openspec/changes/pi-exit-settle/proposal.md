# pi-exit-settle

## Why

Issue #676（#674 后实测残余）：server 端 chat.turn 300s 无响应——pi 本体早已退出，但**扩展派生的 MCP 子进程继承 stdio 管道**，Node 的 close 事件等待所有管道写者关闭→永不触发→runPi 永不 settle→RPC 永不响应（用户：消息发不出来）。

## What changes

- runPi **settle on exit**（pi 本体退出即结算，取已累积 stdout）——不等待 close（孙进程霸占管道场景）；detached 进程组 + 超时 **SIGKILL 整组**（扩展无视 SIGTERM）；信号/超时/退出码分型错误。

## impact_scope

- `webui-server/src/pi-run.ts`
- tests: `webui-server/test/pi_run.test.ts`（重写：grandchild 占 stdio 场景/组杀/表达式替身）
