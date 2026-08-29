# Proposal: alpha3-bounded-pilot

## Why

issue #335: alpha3 的 ~21 个剩余 issue 排序只有口述归因、无证据。需要一个
有界、可复现的 A1-vs-A2 配对试点按管线阶段归因质量差异。

## What Changes

1. evaluation/pilot/paired-pilot-v1.json — 10 案例 × 4 域（≥2）manifest，
   双臂锁 commit/同模型 revision，非 holdout（#84 密封语料尚不存在，案例
   取自公开语料族）。
2. evaluation/pilot/rubric-v1.md — 4 阶段 × 3-5 维 × 0-3 锚定评分，无综合
   分；盲评协议（arm-a/arm-b 匿名，一次过提交）。
3. evaluation/pilot/run-pilot.md — 可复现执行说明（隔离工作区、过程指标、
   降级纪律）。
4. evaluation/pilot/validate.py + tests/test_paired_pilot_manifest.py —
   stdlib 白名单校验（缺字段/revision 不一致/案例数越界/域不足/holdout
   重叠均 fail；RED 阶段真抓出 recovery/recursive-discovery 各缺 1 案例
   并逼出修正）。
5. docs/evaluation/research/pilot-report-v1.md — 框架完整、两臂 not-run
   显式声明、零伪造分数。

## Impact

纯新增（evaluation/pilot/、一个测试文件、openspec change、报告）；
不动 src/；不动 findings-reconciliation.md §6（Phase 4 拥有）。
