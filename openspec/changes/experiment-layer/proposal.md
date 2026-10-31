# experiment-layer

## Why

Issue #567 (T2 row 5, docs 01 L4 实验层): 预注册（假设/判别判据/最小样本量/成本上限，先注册后执行）+ 序贯停止（SPRT 式，后验过阈即停）+ 阶梯硬门（超限=experiment-gated 进风险登记，不跑）+ 设计者不执行（防 rigged）。无外部依赖（克制清单）。

## What changes

- `experiments/layer.ts`: ExperimentLayer over the #547 experiments table —
  `register` (pre-registration validation: hypothesis/criterion 非空, min_sample≥1, cost_cap>0; 先注册后执行),
  `execute` (设计者≠执行者 check, registered→running),
  `recordObservation` (SPRT sequential stop at posterior 0.95, min_sample 下限),
  `checkBudget` (estimated_cost 超过预注册 cost_cap → experiment-gated, 不跑).
- Persistence via LedgerStore.upsertExperiment/getExperiment (migration v3 table, no schema change).

## impact_scope

- `rt-core/src/experiments/layer.ts` (new)
- tests: `rt-core/test/experiments.test.ts`
