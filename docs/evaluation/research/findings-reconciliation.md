---
type: research-reconciliation
topic: alpha2-0aa67a7-reconciliation
status: 核销稿（对真 alpha2 基线 0aa67a7，替代旧调研矩阵的失效部分）
audience: alpha3 立项决策
date: 2026-08-29
baselines:
  - 旧调研基线（失效）: 本地 master db7e256（= alpha1 src，2026-08-07）
  - 正确基线: origin/master 0aa67a7（tag 0.1.0-alpha2，2026-08-22）
method: 2 个核销 worker + 主会话独立验证；全部锚点 `git show 0aa67a7:` 取证
---

# 差距核销：旧调研 65 条 gap 在真 alpha2（0aa67a7）上的命运

> **为什么有这份文件**：4 份旧调研（findings-claim-graph / recursive-round / method-enumeration / stage-gate-reentry）锚定的 commit `db7e256` 落后真 alpha2 发布 485 个提交。旧调研的"应有"侧（29 条属性）全部有效；"现状"侧需逐条核销。本文只做核销与重判，不重复"应有"论述。

---

## 0. 一图总览

```
旧调研断言的 65 条 gap
├── 已解决 / 大幅领先（旧调研说缺，0aa67a7 已有）→ ~14 条
├── 部分解决（机制在，接线/粒度/范围不足）        → ~10 条
└── 仍成立（机制不存在）                          → ~14 条（+行为层断层，新增发现）
```

**六个剩余真缺口**（alpha3 立项对象）：
1. 两个 claim 世界未打通（对齐期 ⊥ 研究期）
2. autonomy 双点锁死
3. supersession disposition 写死
4. 方法枚举无领域维度
5. 递归下降（父子节点/decompose/深度上限）全缺
6. **行为层-运行时断层**（新发现，贯穿性）

---

## 1. A 组核销：Claim Graph（旧 16 条）

| 旧断言 | 0aa67a7 实况 | 判定 | 锚点 |
|---|---|---|---|
| 无 claim 值对象 | `claims.py`：Claim 10 字段（claim_id/subject/predicate/value/polarity/scope/version/time_range/conditions/platform/modality）+ ClaimState 6 态（candidate/isolated/corroborated/rejected/superseded/contested）+ ClaimAdmissionEvaluator（corroborated 需 ≥2 独立 provenance cluster，union-find 聚类防镜像源假独立） | **已解决** | `claims.py:59-72,18-23,141` |
| 矛盾只有 contradicts 边 | `contradictions.py`：7 维 scope 比对（scope/version/time_range/platform/condition_mode/conditions/modality）+ 极性/数值/文本冲突检测 + 8 态分类（candidate-conflict/scope-separated/contested/resolved-a/resolved-b/both-limited/superseded/unresolved）+ resolution chain 验证 + retraction invalidation 传播 | **已解决**（但无"条件/结论/隐含"三分类） | `contradictions.py:33-41,93-144,231-253` |
| compile 无冲突报错 | 交付期矛盾门完整：unresolved_claim_ids + blocking_contradictions + invalidating_contradictions → `InvalidDeliveryError`；closure `no_selected_option_contradiction` 硬检查阻塞 slot 关闭 | **已解决**（研究期/交付期）；**对齐期仍无** | `delivery.py:1368,1381,1388,1409-1411`；`closure.py:1001-1002,1015` |
| alignment_graph 无 claim 节点 | NODE_TYPES 17 种仍无 `claim`；节点无 speech_act/claim_kind 字段；`authority` 是节点类型不是字段 | **仍成立** | `alignment_graph.py:29-49,32` |
| 对齐期声明与 claim 世界无桥 | alignment_graph 0 处 import claims/Claim；compile_handoff 的 baseline finding 的 claim 仍是字符串 observation（`"claim": source["statement"]`） | **仍成立**（= 剩余缺口 #1） | `alignment_graph.py` 全文 grep=0；`:484` |
| Claim 无 speech_act/claim_kind/authority 元数据 | claims.py 的 Claim 也没有这三维度（只有证据侧字段） | **仍成立** | `claims.py:59-72` |
| interaction_state 未接入 | `alignment_protocol.py:18,357` 桥接（reduce_interaction）；PropositionStance（agree/reject/uncertain/correct）用于交互 reduce；但 alignment_graph 不消费它——两套并存 | **部分** | `alignment_protocol.py:18,357` |

## 2. B 组核销：跨轮继承 + 递归下降（旧 17 条）

| 旧断言 | 0aa67a7 实况 | 判定 | 锚点 |
|---|---|---|---|
| tree_state strict-keys 锁死（B 的最硬卡点） | **已改为** `required <= set(value) or extra` 白名单模式——新字段可写入（extra 显式拒绝，需一并放开） | **已解决**（大半） | `tree_state.py:144` |
| expected_transition=0 无继承入口 | 仍无 `initialize_inherited` / `parent_tree_revision_id` / `recursive_round` / `inherited_slots`（全文 grep 空） | **仍成立** | grep=0 |
| supersession disposition 写死 superseded | `active_work` 条目仍硬编码 `"disposition": "superseded"`；无 inherit_kind/recursive_inherit | **仍成立** | `feedback.py:559` |
| record_same_round_replan 仅 work item 粒度 | payload schema 仍严格白名单 `{"id","round_id","classification","feedback_input_id","reason","affected_work_refs"}`——不含 decision_slot/claim/tree_node | **仍成立** | `feedback.py:927,936-941` |
| **（新发现）修正机制已超越旧调研想象** | `CorrectionEvent`（kind: correction/reopen × relation: supersedes/reopens × actor: human/operator）+ `apply_correction`：精确 quarantine 受影响 artifact（5 角色绑定：intent_model/working_brief/decision_map/strategy/handoff）+ **依赖闭包传播**（while 循环遍历 parent_refs 找全部下游）+ 传递性失效（interaction_state:226-237 级联作废 pending actions/assumptions）+ 回 alignment 带 3 项 obligations（alignment_reconfirmation/strategy_reprojection/handoff_reconfirmation） | **大幅领先**（旧调研完全没看见） | `feedback.py:46-67,81-97,130-160`；`coordinator.py:964-1055,1608+` |
| coordinator 无同轮修正 | `record_correction(reason, affected_refs)`——任意 artifact refs，不改 run 身份 | **部分**（run 级有了，tree/slot 级没有） | `coordinator.py:743-772` |
| 递归下降字段全缺 | `recursive_search.py` 节点仍无 parent_node_id/depth/expansion_status；无 decompose_question；node_id 仍 `node:{slot_id}:{digest}` 扁平 | **仍成立** | `recursive_search.py:675-695` |

## 3. C 组核销：方法枚举（旧 15 条）

| 旧断言 | 0aa67a7 实况 | 判定 | 锚点 |
|---|---|---|---|
| method_switch 从未触发 | `policy.py:405-414`：信号驱动真实触发（method_limitation 信号 / missing 含 method_switch → kind="method_switch" + method_boundary 约束）；closure 检查失败也 append method_switch successor | **已解决** | `policy.py:405-414`；`closure.py:1010-1014` |
| 无方法注册/执行追踪 | `search_portfolio.py`（1819 行）：MethodRegistration（method_id/provider_id/capability/failure_boundary/availability/degradation_reason）+ MethodExecutionOutcome（记录 provider 边界每次执行的 outcome/disposition/query_refs/capture_refs）+ Portfolio 4 态生命周期 + batch 决策（stop/rewrite/switch/deepen/experiment/pivot/broaden/validate） | **已解决** | `search_portfolio.py:238-250,892-904` |
| 单 provider 无降级语义 | DEGRADATION_REASONS 含 single-provider/provider-outage/rate-limited…（降级必须显式声明，不可静默） | **已解决** | `search_portfolio.py:27-35` |
| Finding Pack 无 methods 记录 | payload 增 claims/claim_groundings/claim_assessments（Claim 对象化）；但**无** methods_attempted 字段——方法追踪活在 search_portfolio lineage 侧，未进 Finding Pack 本体 | **部分** | `ledger.py:116-130` |
| 方法集合无领域维度 | MethodRegistration 无 domain 字段；WORK_METHODS 仍 6 项全局扁平；intake 仍不收 domain | **仍成立**（= 剩余缺口 #4） | `search_portfolio.py:241-246`；`work_items.py`；`intake.py` |
| search_portfolio 未接线 | coordinator.persist_search_portfolio_lineage 消费（绑定 intent/brief/strategy/decision_map 四路 lineage + pivot_correction 校验）；但 orchestration 波次仍按 4 phase 切，不按方法池切 | **部分** | `coordinator.py:770-815` |

## 4. D 组核销：阶段门/重入（旧 17 条）

| 旧断言 | 0aa67a7 实况 | 判定 | 锚点 |
|---|---|---|---|
| 6 套状态投影分裂、无 canonical | `coordinator.py` 13 态 LIFECYCLE_STATES（alignment/handoff_pending/autonomous_research/synthesis/readiness/delivery_pending/awaiting_acceptance/completed/paused/blocked/superseded/authority_blocked/failed）+ 每边权威标注（human/coordinator/human_or_operator）+ **矩阵外置 JSON**（lifecycle-matrix-v1.json，代码与治理共享一边集） | **已解决** | `coordinator.py:61-73,150-172,185+` |
| 交付前无人类 gate | awaiting_acceptance → delivery_accepted（**human 权威**）→ completed；还有 needs_deeper_research → autonomous_research、intent_correction → superseded 两条人类决议边 | **已解决** | `coordinator.py:68,164-167` |
| research 期重大矛盾无重入 | `apply_contradiction`：矛盾包（8 维 shared_scope 比对）→ **打回 alignment** + blocks [decision,readiness,delivery,closure,task_release,completion] 六类推进 + stale 交付标记 + 独立方法约束（"successor must not reuse the disputed extraction or provenance cluster"） | **大幅领先** | `coordinator.py:1108+,1383-1413` |
| CLI 无状态查询 | cli.py 存在（523 行）：run/resume/status/verify/install/doctor + 内部 coordinator 子命令（ingest/recover/why-not-complete/complete） | **已解决** | `cli.py:50-106` |
| autonomy 写死 | 写入点 `feedback.py:535-536` + validator `:869-872` 双点锁死；policy.py（研究策略）与 preferences.py（偏好学习）均无 ask-user 概念 | **仍成立**（= 剩余缺口 #2） | `feedback.py:535-536,869-872` |
| 被打断无二分门 | CorrectionEvent 有 correction/reopen 之分（接近二分），但**无显式 reentry_kind ∈ {discussion, supplement}**，且 SKILL/adapter 层不知道如何触发它（见缺口 #6） | **仍成立**（半） | `feedback.py:46-48` |
| next_action 字符串 | `coordinator.py:136` 仍是 `str \| None` 非结构化 | **部分** | `coordinator.py:136` |

## 5. 行为层核销（旧调研盲区，新发现）

| 检查项 | 结果 |
|---|---|
| SKILL.template.md vs alpha1 | +27 行：activation 状态机（verified_load→bounded_reconnaissance→alignment_question→explicit_handoff→autonomous_dispatch）+ uv 执行合约。**交互行为规则正文与 alpha1 相同** |
| research-quality-playbook.md | **逐字节相同**（diff=0） |
| apply_correction / apply_contradiction 的调用者 | **仅 coordinator 自身 + tests**。SKILL/adapter/hooks 零调用 |
| adapter 与 runtime 的契约面 | 仅 6 个 CLI 命令（install/doctor/run/resume/status/verify）+ context-seal/probe-host 等 digest 纪律。correction/contradiction/reentry API 不在任何行为层文档中 |

**结论**：runtime 长出了治理器官（13 态生命周期、矛盾重入、修正隔离、交付验收），但**行为层没有神经连上**。"机械、跟 harness 对话"的体验 = 行为层未变 + 其上新叠的治理约束更重。这是剩余缺口 #6，也是让前 5 个缺口修复生效的**总开关**。

---

## 6. 修正后的 alpha3 capability 形态（供 synthesis v2 使用）

| Capability | 旧形态（作废） | 修正形态 | 剩余工作估计 |
|---|---|---|---|
| A: canonical-claim-graph | 从零建 claim 模型+矛盾分类+冲突门 | **桥接两个 claim 世界**：对齐期意图声明对象化（alignment_graph 加 claim 元数据或复用 claims.py 的 Claim）+ compile_handoff 接矛盾门 + speech_act/claim_kind/authority 三维度（claims.py 加字段） | ~6-8 work items（原 16 → 砍半） |
| D: stage-gate-and-reentry-binary | 从零建二分门+canonical state | **autonomy 解锁（双点）+ reentry_kind 显式化 + 行为层接线**（SKILL/adapter 增补被打断→CorrectionEvent 的调用协议）——canonical state/人类 gate 已有 | ~4-5 work items |
| C: method-enumeration-discipline | 从零建方法池+多 provider+触发 | **领域维度注入**：intake 收 domain → METHOD_POOLS 领域化 → search_portfolio/orchestration 接线 + Finding Pack 补 methods_attempted | ~4-5 work items（原 15 → 砍 2/3） |
| B: recursive-round-inheritance | strict-keys 解锁+继承 service | strict-keys **已解决**；剩 supersession disposition 参数化 + inherit_kind + 跨轮 tree 继承入口 + record_same_round_replan 扩 slot/claim 粒度 | ~5-6 work items |
| 6.2: recursive-descent | 从零建 | 基本不变：节点树字段 + decompose_question/prune/evaluate + max_depth + 每层重枚举（与 C 联动） | ~3-4 work items |
| **新增：行为层接线**（贯穿） | 无 | SKILL/playbook/adapter 三层的更新：被打断协议、状态回显协议、correction 调用、对齐期 claim 抽取行为 | ~2-3 work items |

依赖序不变：A → (D ∥ C) → B → 6.2；行为层接线与 D 同批。

## 6.1 Batch-1 落地记录（2026-08-30，主会话）

alpha3 第一批 4 issue 全部合入 dev（squash）：

| Issue | PR | 落点 | 状态 |
|---|---|---|---|
| #337 工程基线（追加） | #338 fddb05c | ruff 扩展门+格式收口+CI 两门 / pydantic 边界+ADR-007 / Docker 探针 / 脚手架收口 | merged |
| #331 治理语言 | #339 9c88cf0 | 四档 tier + per-issue gate 声明 + 测试锁定 | merged |
| #332 行为层接线 | #340 f553aaf | SKILL/playbook/3 adapter 协议段 + 契约测试(10) | merged |
| #333 调度收敛 | #342 c6f2639 | orchestration.py 删除；policy 接线 dispatch（policy_proposal_id 入 lineage）+ADR-006 | merged |
| #335 试点 | #343 e1ffad8 | 资产+rubric+校验(6)+报告——**两臂 not-run**（无 host 通道） | merged |

**第二批排序的证据状态**：试点（#335）交付了框架但零执行数据。因此第二批
排序仍以本文件 §1-6 的调用图/审计证据为准，以下建议按该证据排序，试点
数据可用后复核：

1. **协调器拆分**（#333 收敛后的自然下一步）：coordinator.py 2845 行在
   dispatch 已成唯一权威后是唯一结构性热点；
2. **两个 claim 世界桥接**（剩余缺口 #1）：#332 已让行为层引用 claim 协议，
   alignment_graph ↔ claims.py 的对象化桥接是下一个语义缺口；
3. **试点执行**（带真实 host 环境的运行，填 pilot-report 数据）；
4. 其余（autonomy 双点、supersession 参数化、方法枚举领域化、递归下降）
   按依赖序 A→(D∥C)→B→6.2 不变。

无证据支持的项（试点未跑）：凡涉及"A2 更好/更差"的方向性判断均待试点数据。

## 6.2 Batch-2 落地记录（2026-08-30，主会话）

alpha3 第二批 16 个 issue（含 6 个 post-batch + 4 个 wave 4 ledger 改写）全部合入 dev（squash）。plan：`.claude/PRPs/plans/alpha3-batch2-foundation.plan.md`。

| Wave | Issue | PR | Commit | 落点 | 状态 |
|---|---|---|---|---|---|
| 0 | #326 host_attempts | #349 | a597e7e | 7 disposition + `worker_finished_eligible` | merged |
| 0 | #327 freshness | #350 | 3f009b3 | `FreshnessPolicy` + `assess()` 5 dispositions | merged |
| 0 | #328 heterogeneous-install-plan | #357 | 66db780 | `plan_heterogeneous_install` per-host data | merged |
| 0 | #325 lifecycle facade | #371 | 163d3e7 | `_verify` reads canonical, `_doctor` 4-section | merged |
| 1 | #314 problem forest | #352 | 90c291c | `ForestSpace` (5) + `ReconciliationKind` (8) | merged |
| 1 | #316 claim+speech_act+authority | #356 | 7abf602 | `SpeechAct`/`BELIEF_STATUSES`/`transition` | merged |
| 2 | #315 cognition (4 forests) | #358 | 11938f2 | `compute_alignment_per_branch` | merged |
| 2 | #317 disagreement | #361 | 0ef2f73 | `PressureSignal`/`PressureLedger` | merged |
| 2 | #318 growth-aware readiness | #363 | c55e970 | `BranchState` per-branch handoff | merged |
| 3 | #324 orthogonal state regions | #364 | 72f0fa7 | `STATE_REGIONS` 5-tuple + cross-region fail-closed | merged |
| 3 | #329 progress delta | #365 | 2b4b848 | `ProgressDelta` + `project_delta` | merged |
| 3 | #320 state projection | #368 | ecd0311 | `StateProjection` 11 facets | merged |
| 3 | #334 best-of-N | #370 | f3addcc | `select_candidate` + P0 single-candidate guard | merged |
| post | #322 host capability (Pi) | #373 | 698515a | Pi discovery + governed compat path | merged |
| post | #319 reconnaissance | #375 | 244fa4a | `ReconnaissancePlan` ≥2 methods | merged |
| post | #321 shared brief | #377 | 884a508 | `SharedBrief.from_workspace` evidence chain | merged |
| post | #323 black-box regression | #379 | 3901624 | `BlackBoxFixture` + `score_run` | merged |
| post | #330 operating model | #380 | cc6fa80 | `OperatingModelProjection` + role/SLA | merged |
| Wave 4 | #84 benchmark (rewritten) | — | 659693f (master ref) | alpha2 relocation + rolling-Alpha tier | merged |
| Wave 4 | #67 epic (rewritten) | — | — | close per #331 rolling-Alpha policy | merged |

**Batch-2 治理账本（meta-arbitration 2026-08-30）**：3 个审查 subagent（code-review / ponytail-review / silent-failure-hunter）独立 FAIL，识别 7 条 BLOCKING（4 CRITICAL + 3 HIGH）。见 `.claude/PRPs/reports/alpha3-batch2-meta-arbitration-2026-08-30.md` 与对应 issue #381-#387。Batch-2 fixup 详见 `.claude/PRPs/plans/alpha3-batch2-fixup-silent-failures-and-governance.plan.md`。

## 7. 本核销的边界与未验证项

- 全部锚点来自 `git show 0aa67a7:` / `git grep ... 0aa67a7`，未运行测试（判定基于代码结构与调用关系）。
- worker A+D 曾误报 cli.py 不存在，已主会话复核纠正（`git show 0aa67a7:src/research_tree/cli.py | wc -l` = 523）。
- 外部业界对照（Zeno/STORM/Tree of Thoughts 等）三次派发均因环境 API 400 失败，未完成——如需再做，建议换网络环境重试。
- `git pull` 为纯 fast-forward（HEAD=db7e256 是 0aa67a7 的祖先，已验证）；唯一注意：5 个本地 untracked 文件会被 origin 完成态版本覆盖（openspec/changes/add-durable-interaction-state/* + tests/test_durable_interaction_state.py）。

## 6.3 Batch-3 记录（mainline purge + goal wiring，2026-09-01）

§5/§6.1/6.2 记录的"行为层-运行时断层"与"合并未接线"病在 goal 域复现并被本批根治：

- **审计附录 A1**（#420 开工前）发现 StrategyProjection 生命周期（display_strategy/confirm_handoff）与 alignment_handoff.initialize_research_from_alignment 均为**零生产接线**——与 #320/#329/#330/#334 同病。#427 按 R1 修订以 CLI strategy 动词接线（host event 为 non-authoritative 载体不承载确认权威），confirm→initialize_research_from_alignment 桥接打通"确认→建树"。此为 F1 断层在 goal 域的闭环。
- **A6 教训（R4）**：§A6 字面 grep 门与 merge 设计互斥（wire 值必须保留）——规格字面门需与设计路线同时校订。**A7 教训（终审#1）**：§A7 字面文件集过时（feedback.py 从无此二函数）——归档账本按意图口径备案。
- **registry 悬空引用缺陷类**：#420-#428 五个 PR 连续在治理 registry 中发现/修复 dangling 路径引用（机械门按历史 revision 校验不查 HEAD 存在性）。#445 落地 `missing_tests_entrypoint` 机械门禁后该类永久关闭——验证"机械门禁优先于人工扫描"（maker-checker 规则）。
- **捎带覆盖丢失**（#420 复审 HIGH）：删除测试文件时锚定幸存行为的用例被静默连带删除，pytest 全绿掩盖之。终审以 settrace 机械追踪 + 变异注入确认恢复有效性。教训：删测试与删代码需独立对账。
- **输出腐坏事故群**：多个 maker 会话出现长文本编辑损坏（alignment_handoff.py 整文件覆盖、cli.py 吞 def main、project_workspace 手术损坏）——全部被"全量 diff 复查 + 全量测试"兜住，无一入库。长文件编辑应优先脚本化行区间操作。
- 终态：**§A-§D 全绿 + 对抗终审×2 零 CRITICAL/HIGH**（验收记录：docs/evaluation/research/batch3-acceptance-record.md）。goal 环（confirmed→serves→贡献判定→完成门）首次全链进入生产路径；R3 助纠协议（苏格拉底澄清/坚持→警告→照做+waiver）同时落地于 runtime 校验与行为层锚句。
