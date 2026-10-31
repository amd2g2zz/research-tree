# overnight-run

## Why

Issue #569 (T2 row 7, charter H6): 12h 无人值守过夜跑可信。全局预算硬帽强制收敛（永不挂起）；信息/预算不足时 PARK 兜底（带复活条件，产品红线）；崩溃恢复——中途引擎崩溃从事件日志续跑，不重启账本、无账本损坏。

## What changes

- `headless/overnight.ts`: runOvernight + recoverFromCrash —
  **12h 硬帽强制收敛**（注入时钟；到帽跑一轮 final 轮：info_sufficient → forced convergence，否则 PARK）；**PARK 必须带复活条件**（空复活条件拒绝，红线）；**轮数上限 fail-closed**（不收敛不推进时钟的 round executor → PARK 而非空转）；**崩溃恢复协议**（verifyGraphChain 防篡改 → rehydrate 自 task.transition 事件 → 续跑）。
- 研究轮本身由调用方供给（mock-e2e harness / pi extension 驱动实际循环）；本模块只拥有无人值守可靠性机制。

## impact_scope

- `rt-core/src/headless/overnight.ts` (new)
- tests: `rt-core/test/overnight.test.ts`
