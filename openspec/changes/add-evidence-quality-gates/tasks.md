# Tasks: add-evidence-quality-gates

## 1. E2 实验（先实验后实施，§8-E2）

- [ ] 1.1 黄金集 fixtures：`webui-server/test/fixtures/golden-relevance/`——
  医院研究任务 × {医院相关源, 游戏源, 太空源, 音频转录源, 空结果}（取材
  dogfood ISSUE-004 真实失真样本）+ golden-labels.json（人工标注）。
- [ ] 1.2 启发式打分纯函数（bigram 重叠）跑黄金集，记录逐案 verdict/延迟。
- [ ] 1.3 pi 单批判定（真实 pi 二进制采样一次），记录逐案 verdict/延迟/成本。
- [ ] 1.4 择优结论 + 数据表写入 design.md；若 pi 胜出则判定调用必须过
  budget/stop 守卫（本 change 选用折中：启发式常开 + 综合 JSON 融合 verdict，
  无新增付费调用——守卫天然满足）。

## 2. StageOutcome 结构化（RED first）

- [ ] 2.1 RED: `rt-core/test/stage_outcome.test.ts`——parseStageOutputs 对
  legacy artifact / StageOutcome / 损坏 JSON 三形态的归一化（legacy 显式标注
  + 原文保留，损坏 fail-closed 到 unknown）。
- [ ] 2.2 RED: ledger migration v11——旧行重写为 StageOutcome（篡改检测式：
  迁移后 legacy 字段逐字节等价于原 artifact）。
- [ ] 2.3 GREEN: `rt-core/src/scheduler/stage_outcome.ts` + ledger v11。
- [ ] 2.4 RED/GREEN: completeStage 收 StageOutcome + recordOutcome（写产出
  不改状态）；画布 projection 读结构化产出（含 parked 的 unresolvedClaims）。

## 3. 充分性门（RED first）

- [ ] 3.1 RED: 无关源（游戏/太空 vs 医院）→ 不完成；stated gain 重查一轮；
  仍不足 → parked + unresolvedClaims 持久可见。
- [ ] 3.2 RED: 空结果 → 不完成 → park；冲突源 → 不完成，conflict 入
  unresolvedClaims。
- [ ] 3.3 GREEN: execute 门逻辑 + relevance.ts 启发式 + 综合结构化输出
  （sourceVerdicts/sufficiency/unresolvedClaims，向后兼容旧输出形态）。
- [ ] 3.4 GREEN: 综合失败 ≠ 完成（既有"诚实降级仍 complete"测试翻转为
  parked + unresolvedClaims——这是 #744 的行为修复本身）。

## 4. 无进展停（RED first）

- [ ] 4.1 RED: 同任务重复查询 → 不再付费检索，直接停泊（stopReason=
  no-progress-duplicate-query）。
- [ ] 4.2 RED: 连续近重复发现 → 任务级无进展旗标 → 仲裁员拒绝生长 +
  图诚实闭合（broadcast 命名停条件）。
- [ ] 4.3 GREEN: 机械触发器落地（每条停条件一个可断言的 stopReason）。

## 5. 汇总覆盖语义（RED first）

- [ ] 5.1 RED: closeGraphIfComplete 注册 `汇总｜<根问题>`（首分支 ≠ 根问题
  时标题仍正确——ISSUE-006 回归）。
- [ ] 5.2 RED: 汇总产出 coverage 枚举全部分支（answered/gap）；仲裁 prompt
  收根问题。
- [ ] 5.3 GREEN: seedBranches 复活为 seedTaskContext（根问题+分支），server
  research.start/mindmap 确认路径接线。

## 6. 阻尼任务隔离（RED first）

- [ ] 6.1 RED: 交错两任务，任务 B 高增益后验不改变任务 A 的阻尼演化
  （串行 vs 交错同一例子等价——evaluation 文档要求的回归）。
- [ ] 6.2 GREEN: taskLastPrior per-task Map 替换共享 lastPrior +
  priorByStage.size 判断。

## 7. 收口

- [ ] 7.1 TDD 矩阵全绿（无关/空/冲突/无进展/隔离/每条停条件机械触发）。
- [ ] 7.2 本地门全绿：pytest / ruff / delivery validate / openspec
  governance / `openspec validate add-evidence-quality-gates --strict` /
  rt-core & webui-server & webui check+test(+build)。
- [ ] 7.3 GitNexus：被改符号 impact 存档 + detect-changes --scope all +
  PR 证据（compare vs dev）。
- [ ] 7.4 PR：rebase 最新 dev → check-pr 干跑 → gh pr create（Closes #744），
  CI 全绿后交编排者（合并序列 #742 先、#744 后，不自行 merge）。
