# Design: alpha3-batch1-foundation

## Context

基线 `0aa67a7`（已发布 0.1.0-alpha2）。本 change 覆盖 4 个已确认 issue（#331 #332 #333 #335），全部依据 2026-08-29 核销审计（`docs/evaluation/research/findings-reconciliation.md`）的调用图证据：

**行为层现状**：`skill-src/SKILL.template.md` 较 alpha1 仅 +27 行（激活状态机 + uv 执行合约）；`references/research-quality-playbook.md` 与 alpha1 逐字节相同；`apply_correction`/`apply_contradiction`/`record_correction` 在 skill-src/hooks/scripts 的引用数为 0。行为层与 runtime 的唯一契约面是 6 个 CLI 动词（install/doctor/run/resume/status/verify）与 digest 纪律（context-seal/probe-host）。

**调度层现状（三个平行世界，全部验证过消费者）**：

| 层 | 消费者 | 状态 |
|---|---|---|
| `orchestration.py`（358 行，4-phase 波次编译） | 仅 `__init__.py` re-export；tests 零引用 | 死代码，但 packages/ 文档仍教其词汇 |
| `policy.py` / `AdaptiveResearchPolicy`（564 行，含 replay/calibrate） | 仅 `__init__.py` re-export + `test_adaptive_policy.py`/`test_policy_replay.py` | 活代码无生产接线 |
| `coordinator.py::dispatch`（2845 行类内） | CLI + tests | 生产路径，逐 work-item 手动派发，内嵌 strategy-projection/decision-frame/authority 三重校验 |

**约束**：Python 3.11+ / uv / 零运行时依赖；测试 104 文件无 conftest（`tmp_path` 风格）；CI 质量门 = `pytest -q` + `ruff` + 5 个 `scripts/check_*.py`；PR 合并为 squash；分支惯例 `{type}/issue-{N}-{slug}`。

## Goals / Non-Goals

**Goals:**
- G1（#332）：被打断/矛盾/验收/claim 抽取四类交互场景从行为层可触达具名 runtime API，且由契约测试永久锁住"文档引用的 API 必须真实存在且签名匹配"。
- G2（#333）：调度收敛为单一权威——`compile_orchestration_plan` 消失于公共 API；`AdaptiveResearchPolicy` 进入 `coordinator.dispatch` 生产路径（保留 replay/calibrate）；ADR-006 记录决策。
- G3（#335）：A1 vs A2 有界配对试点的资产（manifest/案例/rubric/报告）与归因产出，为第二批 ~21 issue 排序提供证据。
- G4（#331）：发布治理语言四档化，绝对化表述消除。
- G5：4 分支 4 PR 全部过本地等价质量门后 squash 合入，无巨型 commit。

**Non-Goals:**
- 不改 claims/contradictions/closure 语义（已验证为正确资产）。
- 不做 #314-#318/#324 认知模型系（第二批，等 #335 证据）。
- 不做 #334 best-N（依赖 G2 收敛完成）。
- 不做 coordinator.py 大拆分（本批只做调度层收敛；上帝对象拆分留第二批）。
- 不跑全量 benchmark（#84）；试点 host 不可用时按 #268 纪律降级 not-run 交付。
- 不新增运行时依赖；不引入 conftest。

## Decisions

### D1：行为层接线用"文档→API 契约测试"而非运行时 wrapper
四协议段直接写入 SKILL/playbook/adapters（`- When {触发}, use {API} {约束}` 句式，取自 claude-adapter.md:61-64 先例）。**不**为 correction/contradiction 新建 runtime wrapper 模块——runtime API 已存在且经过测试，缺的是行为层知道它们。锁真伪的手段是 `tests/test_behavioral_layer_contract.py`：名单制提取文档中反引号内的 `research_tree` API 名 → `importlib` 验证存在 + `inspect.signature` 验证文档所述关键参数。备选"为每个协议建 python entry 脚本"被否：增加第四层包装，重复 #333 正在消除的病。

### D2：orchestration 摘除而非保留兼容
全库 grep 证明 `compile_orchestration_plan` 零外部消费者（tests 亦零引用），故直接删除 + `__init__` 摘导出，不做 deprecation 周期。先例：scheduler.py 在 alpha2 周期即直接 purge（commit ad0356d）。其 4-phase 概念若 coordinator 未覆盖，在 ADR-006 中记录映射关系而非迁移代码。

### D3：policy 接入点选 `coordinator.dispatch` 的策略投影确认点
`dispatch()` 在派发前已校验 strategy_projection/decision_frame（coordinator.py:2313 起，`strategy_projection_confirmation_required` 分支）。`AdaptiveResearchPolicy.propose()` 的输出（PolicyProposal: kind/method_boundary/trigger_refs）在该决策点作为派发依据消费：无 policy 提案时保持现行为（向后兼容），有提案时记录 proposal id 于 attempt lineage。**保底备选**（若接线发现 dispatch 语义与 proposal 产物不匹配）：ADR-006 转为退役决策——把 replay/calibrate 迁移到 coordinator 侧，policy.py 删除。两种结局都满足"唯一调度权威"，由 TDD 红绿信号裁决。

### D4：试点归因用 4 阶段 × 双臂盲评，不做综合分
rubric 按 alignment/evidence/synthesis/delivery 四阶段独立打分（每阶段 3-5 个维度，0-3 分），两臂输出匿名化后盲评。**禁止**合成单一总分（#268 纪律：no single aggregate score）。归因 = 阶段间两臂差值的排序 + 每案例方法多样性/溯源组数/claim 准入结局/矛盾数/人工轮次的过程指标。案例不取自 holdout；两臂同 model revision；模拟用户输出只作交互证据不作满意度证据。

### D5：发布治理四档语言固定为枚举
`published`（包可发布）/ `alpha-pilot-suitable` / `org-rollout-ready` / `unattended-final-authority`。每个 open 评测 issue 在治理文档中获得一行 gate 声明（gates X, does not gate Y），消灭"open benchmark → cannot release"推断。#67 正文更新由主会话执行（subagent 不动 GitHub）。

### D6：PR 顺序与冲突消解
331（纯 docs，面最小）→ 332（skill-src+packages+契约测试）→ 333（**rebase on 332**，共享 packages 面）→ 335（报告类，无 src 冲突）。332 与 333 的实际共享面只有 packages/ 再生成，由 rebase 顺序消解；332 不动 `__init__.py`（纯文档+测试），333 摘 orchestration 导出，源头错开。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| D3 接线点语义不匹配（proposal 产物 vs dispatch 期望） | TDD：接线测试先红；不匹配即走 D3 备选（退役迁移），两途都闭环 |
| 契约测试过严（文档措辞变化即红） | 只校验反引号内 API 名与参数名存在性，不校验整句语义；名单制扫描 |
| packages/ 三份再生成漂移 | 332/333 的 PR 门必含 `build_skill_packages.py --check` |
| 试点 N 小被过度解读 | 报告强制"不可下结论"段；第二批决策必须引用数据行 |
| 本地基线 485 提交落后带来的同步意外 | PRP 计划 Phase 0 已含 fast-forward + untracked 处置流程；pytest 基线全绿才开工 |
| 契约测试误报（文档提到历史名词） | 名单制：契约测试仅扫描白名单 API 名集合，新协议段引用哪些 API 名单就含哪些 |
