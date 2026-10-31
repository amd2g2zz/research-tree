# thompson-directions

## Why

Issue #568 (T2 row 6, docs 01 §方向策略): 方向级组合管理。执行并行（#565）之外的另一条机械规则——方向选择本身由 Thompson 采样统治，不用手工 explore/exploit 规则。

## What changes

- `directions/thompson.ts`: DirectionSampler over the #547 directions table —
  **封闭方向来源**（hypothesis-ledger / kill-graph-branch / refuted-variant / survivor-adjacency 四种，其余拒绝）；**硬上限 8 臂**，第 9 个方向 parked（pinned，不顶替）；
  **四信号价值后验**（kill-存活率 / 证据产率 / 决策杠杆 / 意外度 → Beta 后验，均值落盘 value_posterior，信号进 history 可追溯）；
  **Thompson 分配**（种子化可复现采样，整轮预算给采样最高者）；
  **触发器**（make-or-break 悬在 ~0.5 → deepen；全员 EVSI 跌破阈 → widen）；
  **增宽预算结构性封顶 ≤30%**（累计 widen 占比硬约束，超出部分被削减，不靠意志力）；
  **组合面板**（轮边界渲染 方向×价值后验×分配）。

## impact_scope

- `rt-core/src/directions/thompson.ts` (new)
- tests: `rt-core/test/directions.test.ts`
