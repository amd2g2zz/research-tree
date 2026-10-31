# t2-closeout

## Why

Issue #570 (T2 exit, roadmap): 早终止/双席/实验层在 ≥5 个真实想法上工作；12h 过夜跑成功（H6 引擎侧）；验收记录落盘。

## What changes

- `test/t2_closeout.test.ts`: 五想法 T2 退出走查 — doomed-2c4g（早终止+H5 节省≥50%）、contested-cost（双席等预算+反证发现）、parallel-cluster（依赖感知调度+并发帽）、historical-fork（3-click 含历史版本）、experiment-gated（实验全环+超预算→gated）；横切 #568（≤8 臂、widen ≤30%）与 #569（硬帽强制收敛+晨间重放）。
- `evidence/acceptance.md`: 验收记录（逐项 verified / deferred+理由）。
- 附带修复：ExperimentLayer.execute 拒绝 gated 实验（阶梯硬门此前只标记不拦截——验收测试暴露）。

## impact_scope

- `rt-core/src/experiments/layer.ts` (gated-execute guard)
- tests: `rt-core/test/t2_closeout.test.ts`
