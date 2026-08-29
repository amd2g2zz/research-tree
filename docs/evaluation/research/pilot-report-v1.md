---
type: evaluation-report
pilot: paired-pilot-v1
status: not-run（资产交付，两臂均未执行）
date: 2026-08-30
audience: alpha3 第二批排序决策
---

# Paired Pilot v1 Report — EXECUTION STATUS: NOT-RUN

## 0. 执行状态声明（先读这个）

**两臂（A1 / A2）均未执行。** 本文档交付的是试点框架：manifest、rubric、
执行说明、评分与归因的表格结构，以及过程指标骨架。**没有任何分数、没有
任何双臂对比、没有任何归因结论。**

未执行原因：本环境无 host 执行通道（无法安装/驱动 claude-code 会话跑
研究任务）。按 #268 纪律：**missing ≠ pass**——空单元格标记 not-run，
不填 0、不填估计值、不由结构推论。

**在两臂真实跑完之前，本报告不得被引用为 A1/A2 质量差异的证据。**

## 1. 试点身份

| 字段 | 值 |
|---|---|
| manifest | `evaluation/pilot/paired-pilot-v1.json`（10 案例，4 域 × ≥2） |
| arms | A1 = `0.0.1-a1`（8ab91ea）；A2 = dev `c6f2639`（0aa67a7+batch1） |
| model | glm-4.7，同一 revision 双臂锁定（校验强制） |
| host | claude-code 单 host |
| rubric | `evaluation/pilot/rubric-v1.md`（4 阶段 × 3-5 维 × 0-3，无综合分） |
| holdout | 非 holdout：#84 的 24-cluster 密封语料尚不存在；案例取自公开语料族（alpha2-release-v1） |

## 2. 分阶段双臂对比表（结构，全部 not-run）

### Stage 1 — Alignment

| Dimension | A1 | A2 |
|---|---|---|
| intent-capture | not-run | not-run |
| scope-negotiation | not-run | not-run |
| authority-boundaries | not-run | not-run |
| interruption-protocol | not-run | not-run |

### Stage 2 — Evidence

| Dimension | A1 | A2 |
|---|---|---|
| method-diversity | not-run | not-run |
| provenance-discipline | not-run | not-run |
| contradiction-handling | not-run | not-run |
| counterevidence | not-run | not-run |

### Stage 3 — Synthesis

| Dimension | A1 | A2 |
|---|---|---|
| claim-admission-honesty | not-run | not-run |
| decision-support | not-run | not-run |
| uncertainty-honesty | not-run | not-run |

### Stage 4 — Delivery

| Dimension | A1 | A2 |
|---|---|---|
| technical-actionability | not-run | not-run |
| human-brief-fidelity | not-run | not-run |
| acceptance-protocol | not-run | not-run |
| stale-marking | not-run | not-run |

（每格真实执行后填：10 案例 × 维度 × 双臂的中位差与分布，非单一数字。）

## 3. 阶段归因排序（结构，无数据）

执行后填写规则：按阶段的（A2−A1）维度差排序，只比阶段内维度，不跨阶段
加权。预期观测点（假设，非结论）：

1. interruption-protocol / stale-marking 维度应是 #332 接线的直接收益面；
2. method-diversity / claim-admission 应反映 alpha2 治理机器（#333 后由
   coordinator 单一权威驱动）；
3. alignment 阶段差异预期最小（两版行为层文档同源）。

## 4. 过程指标表（骨架）

| Metric | A1 | A2 |
|---|---|---|
| method-diversity（每案例中位） | not-run | not-run |
| provenance-groups（每案例中位） | not-run | not-run |
| claim-admission outcomes（corr/iso/rej） | not-run | not-run |
| contradiction count | not-run | not-run |
| human turns | not-run | not-run |
| correction-events（仅 A2 可有） | — | not-run |
| stale-deliveries（仅 A2 可有） | — | not-run |

## 5. 不可下结论范围

- 不得由本文件推断 A1/A2 任何质量差异；
- 不得由框架存在推断试点已验证；
- 第二批排序在两臂执行前继续以调用图/审计证据为准（见
  findings-reconciliation.md）；
- 执行入口：`evaluation/pilot/run-pilot.md`；评分纪律：`rubric-v1.md`。
