## 0.5 工程基线升级（主会话，chore(engineering-baseline) PR，先于 #331）

- [ ] 0.5.1 ruff 门扩展：`[tool.ruff.lint]` 加 C90/PLR/PLW/ARG/SIM/B/I；45 存量文件 `ruff format` 一次收口；CI 加 `ruff format --check` 门；存量违例显式豁免（per-file-ignores/noqa），新代码零豁免
- [ ] 0.5.2 pydantic：dev group 加依赖 + `src/research_tree/schemas.py` 试点边界（本批新模块强制注解）+ ADR-007 记录与 stdlib-only 的边界
- [ ] 0.5.3 hermes loader 测试 Docker daemon 探针化（CLI 存在但 daemon 停机 → 显式 skip 带原因）
- [ ] 0.5.4 脚手架/历史文件收口：`docs/方案设计.md`/`docs/需求理解.md` 移入 docs/history/ 或 gitignore；确认 `docs/research/` 零残留；`.research-tree*` 等模式补 .gitignore
- [ ] 0.5.5 chore PR 合入后 4 个 issue 的 worktree 从该 commit 切出

## 1. 基线与工作网格（Phase 0/1，主会话）

- [x] 1.1 备份并让位 5 个 untracked 冲突文件（openspec/changes/add-durable-interaction-state/* + tests/test_durable_interaction_state.py），归档 .research-tree*/ 旧运行态到 /tmp/pre-pull-backup
- [x] 1.2 `git pull --ff-only origin master`，验证 HEAD == 0aa67a744e20485f6122eeaa5f29f8d41ba69f192
- [x] 1.3 `uv sync` + `uv run --frozen pytest -q` 基线绿（969 passed；hermes loader 2 项为 Docker daemon 停机环境红；docs/research→docs/evaluation/research 迁移已修 documentation-governance 红）
- [ ] 1.4 创建 4 个 worktree（/tmp/rt-alpha3-wt/{issue-331,332,333,335}），全部从 origin/master 切分支：docs/issue-331-release-governance-language、feat/issue-332-behavioral-wiring、refactor/issue-333-scheduling-consolidation、eval/issue-335-bounded-pilot

## 2. #331 发布治理四档语言（subagent: governance-doc-specialist）

- [ ] 2.1 RED：为 check_docs.py 增加四档词表与 per-issue gate 声明（`gates <tier>; does not gate <tier>`）的机器校验测试（缺声明/越档表述时失败）
- [ ] 2.2 GREEN：修订 docs/governance/*（documentation-authority.md 等）为四档语言；为 #67/#84/#292/#323 逐一附 gate 声明行；消除"open benchmark → cannot release"类表述
- [ ] 2.3 全门通过（pytest -q / ruff check（CI 同款 diff 范围，勿全量 ruff format --check——CI 无此门且基线 45 文件不过）/ check_docs.py / git diff --check），≤5 逻辑 commit，开 PR `docs(issue-331): align release-governance language with rolling-Alpha policy`，squash --auto 合入

## 3. #332 行为层协议接线（subagent: skill-doc-specialist，PR 序第 2）

- [ ] 3.1 RED：写 tests/test_behavioral_layer_contract.py——白名单 API 集合（record_correction/apply_correction/apply_contradiction/acceptance 决议/research-tree status 字段）在 SKILL.template.md、research-quality-playbook.md、三 adapter 中按名可寻；每个引用名 importlib+inspect 验证存在于 src/research_tree（先红：当前文档无协议段）
- [ ] 3.2 GREEN：SKILL.template.md 增 4 协议段（被打断→record_correction kind 二选一；结论被质疑→apply_contradiction；交付验收→5 决议；对齐期→claim 抽取），句式 `- When {触发}, use {API} {约束}`
- [ ] 3.3 research-quality-playbook.md 重写与 runtime 矛盾段（整图 handoff → 分支/修正语义）+ 增状态回显段（用户可见状态消息前先 research-tree status）；检查 <800 行
- [ ] 3.4 三 adapter（claude/codex/hermes）各增协议入口行；跑 build_skill_packages.py 重新生成 packages/ 并 --check 通过
- [ ] 3.5 全门通过（含 check_skill_activation.py），≤5 逻辑 commit，开 PR `feat(issue-332): wire behavioral layer to runtime governance APIs`，squash --auto 合入

## 4. #333 调度权威收敛（subagent: refactor-specialist，PR 序第 3，先 rebase on #332）

- [ ] 4.1 RED：测试断言 `from research_tree import compile_orchestration_plan` 失败（导出摘除）；测试断言 coordinator.dispatch 决策路径消费 AdaptiveResearchPolicy.propose（monkeypatch 验证调用）
- [ ] 4.2 写 docs/adr/ADR-006-single-scheduling-authority.md（保留/退役层、4-phase 概念映射或弃用理由、备选与否决、回滚条件）
- [ ] 4.3 删 src/research_tree/orchestration.py + __init__.py 摘导出；全库 grep compile_orchestration_plan 零命中
- [ ] 4.4 按 ADR 主途接线 policy.propose 于 dispatch 策略投影确认点（proposal id 入 attempt lineage）；若 TDD 证明语义不匹配则走备选退役分支（replay/calibrate 迁 coordinator，删 policy.py）——两途任一闭环即达标
- [ ] 4.5 packages/ 文档词汇清洗（orchestration→coordinator/policy），build 重生成 + --check
- [ ] 4.6 全量 pytest -q 绿（policy 两个测试文件随接线/迁移更新）；全门通过，rebase on #332 后 ≤5 commit，开 PR `refactor(issue-333): consolidate scheduling into single authority`，squash --auto 合入

## 5. #335 有界配对试点（subagent: evaluation-specialist，PR 序第 4）

- [ ] 5.1 写 openspec 试点资产：evaluation/pilot/paired-pilot-v1.json（8-12 案例四领域各 ≥2，非 holdout）+ rubric-v1.md（四阶段 × 3-5 维度 × 0-3 分，无综合分）+ manifest 模板与校验
- [ ] 5.2 RED：manifest 校验测试（缺字段/两臂 model revision 不一致/holdout 重叠时失败）
- [ ] 5.3 执行两臂（A1@0.0.1-a1 vs A2@0aa67a7，同 model/host，隔离工作区）；host 不可用则按 spec 降级 not-run 交付
- [ ] 5.4 盲评四阶段 + 过程指标（方法多样性/溯源组数/claim 准入结局/矛盾数/人工轮次）
- [ ] 5.5 写 docs/evaluation/research/pilot-report-v1.md（per-stage 双臂对比 + 归因排序 + "不可下结论范围"声明；无综合分）
- [ ] 5.6 全门通过（check_evaluation_assets.py），≤5 commit，开 PR `eval(issue-335): bounded paired pilot attributing quality loss by stage`，squash --auto 合入

## 6. 裁决与收尾（主会话，依赖 #335 合入）

- [ ] 6.1 基于 pilot-report 数据行提出第二批排序建议（无证据支持的项显式标注待复核），更新 docs/evaluation/research/findings-reconciliation.md §6
- [ ] 6.2 确认 4 PR merged、4 issue 自动关闭、origin/master 增 4 个 squash commit
- [ ] 6.3 清理 worktree（git worktree remove），向用户汇报第二批建议并请拍板
