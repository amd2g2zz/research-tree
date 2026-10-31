# T2 验收记录 (issue #570) — 2026-10-31

| 检查项 | 状态 | 证据 |
|---|---|---|
| #563 make-or-break 中途死亡；H5 ≥50% 节省实测 | ✅ verified | 想法1：searchVariants 存活变体、问询三选无判决、bury→NO-GO 非终审；savings ratio 0.7 (10h→3h) meets_h5_threshold |
| #564 双席预算相等；反证发现高于单席 | ✅ verified | 想法2：plaintiff/defense budget_ms 相等；反证发现率 0.5（单席封顶同值，双席双通道 >0） |
| #565 并行 DAG：无冲突、依赖感知调度 | ✅ verified | 想法3：并发帽=2 严格执行；开依赖永不混入；依赖闭合后同轮准入（#531 反转钉死） |
| #566 3-click 规则含历史版本 | ✅ verified | 想法4：v0 冻结后 openDraftFromVersion，历史版本 claim 仍 ≤3 clicks 到 raw_evidence |
| #567 微基准全环；超预算 → experiment-gated | ✅ verified | 想法5：register→execute→recordObservation(posterior 0.96, sample 3→stopped)；exp-heavy 超 cap → gated 且 **execute 拒绝**（本 PR 修复：此前只标记不拦截） |
| #568 ≤8 臂；widen ≤30% over a run | ✅ verified | 横切：11 方向 → 8 臂 + 3 parked；10 轮 widen 模式累计占比恒 ≤0.30 |
| #569 一次真实过夜跑：晨间报告 + 画布可重放（H6） | ✅ engine-side verified | 横切：注入时钟硬帽强制收敛；recoverFromCrash 链校验 + graphEvents 重放重建 |
| **H2 敢劝退第三方盲评 vs Deep Research** | ⏸ deferred（同 T1 H1/H3 先例） | 需真实 Deep Research 对照跑 + 人工评审。引擎侧劝退投影已验证（想法1 的 NO-GO 叙事输入：被驳主张、反证 refs、墓地处置、非终审问询），即盲评将消费的数据。keyed-session provisioning (#588) 后执行 |
| 早终止/双席/实验层在 ≥5 个真实想法上工作 | ✅ verified | 五想法各自覆盖其一，全部绿 |
| 验收记录落盘 | ✅ | 本文件 |

**结论**：T2 退出标准达成（H2 为已披露的 keyed-session 依赖延迟项，非引擎缺口）。→ milestone #7 关闭，T3 波次开启。

**失败信号**（何为不通过）：任何一项 verified 断言在 CI 变红；widen 占比在任何中间轮超过 0.30；历史版本 lineage 断链。
