# Design: add-evidence-quality-gates

## 上下文

issue #744（P0）+ dogfood ISSUE-004/006。SDD 输入含
`docs/evaluation/2026-11-19-reverse-engineering-evidence-and-learning.md` 三处
信号失真：①模型自评标量不能替代逐来源相关性判定；②阻尼基准 lastPrior 全
runner 共享 + priorByStage.size 判断——跨任务串扰；③"保存成功/证据足够/
问题已回答"三事实被压缩成一个 complete。

## E2 实验：相关性判定方案择优（计划 §8-E2）

黄金集（`webui-server/test/fixtures/golden-relevance/`，取材 dogfood ISSUE-004
真实失真样本——医院病历摘要试点任务 × {医院相关源, 游戏剧情源, 太空源,
音频转录源, 空结果, 混合, 冲突}，14 个源级标注 + 5 个门级标注）。

### 方案 a) 启发式打分（纯函数：分命题 bigram 重叠）

迭代三轮（数据为确定性重放，非一次性采样）：

| 轮 | 机制 | 源级严格准确率 | 门级判定 | 假阳性方向 |
|---|---|---|---|---|
| run1 | 整体参照（query+claims 联合）重叠比，阈值 0.20/0.05 | 10/14 = 71.4% | 5/5 ✓ | 无（漏判均保守） |
| run2 | 分命题取 max + 命中数 ≥2（合计计数，跨命题重复计数 bug） | 8/14 = 57.1% | 5/5 ✓ | 2 个 relevant 假阳性（"背景音"击中"任务背景"） |
| run3（定版） | 分命题取 max + **union 去重**命中 ≥2 + **虚词字符组剔除**，阈值 0.15/0.05 | 9/14 = 64.3% | 5/5 ✓ | **0 个 relevant 假阳性** |

定版逐案（2026-11-23 确认轮）：

| case | 逐来源 golden→实测 | 源级 | 门级 |
|---|---|---|---|
| conflicted | rele→rele✓、rele→rele✓ | 100% | conflicted ✓ |
| empty-results | （空结果机械判定，无判定调用） | — | insufficient ✓ |
| dogfood-issue-004-irrelevant | irre→irre✓、irre→unce、irre→irre✓、irre→unce、irre→irre✓ | 60% | insufficient ✓ |
| mixed | rele→rele✓、rele→unce、irre→unce、irre→unce | 25% | sufficient ✓ |
| relevant-hospital | rele→rele✓、rele→rele✓、rele→rele✓ | 100% | sufficient ✓ |

- **延迟**：0.01–3ms/案（纯函数，零网络零调用成本）。
- **可解释性**：逐来源 verdict 携带 basis（重叠分 + 命中组数）。
- 关键教训（run2→run3）：中文滑窗字符组的相邻重叠（"的任务"→{的任,任务}）
  会击穿命中数守卫——"背景音"击中"任务背景"的假阳性根因是虚词"的"；
  虚词字符组剔除 + union 去重后全部 miss 落在保守方向（→uncertain），
  门把 uncertain 与 irrelevant 同等对待（不计入 sufficient）。

### 方案 b) pi 单批判定（结构化 prompt 输出 verdict+basis）

**环境不可用，如实记录**：本机 pi 二进制在场
（`~/.pi/agent/npm/node_modules/.bin/pi`），但模型 API 返回
`402 Insufficient Balance`（账户欠费）。两轮采样（120s×3 案、300s×2 案）
全部挂起到超时，usage 全 0（input/output/cacheRead=0），无一案产出判定。
print 模式 60s 探针复现 402。按任务预案：**只按启发式实施，pi 方案列为
后续**。复跑命令：`RT_E2_SKIP_PI=0 node --experimental-strip-types
openspec/changes/add-evidence-quality-gates/evidence/e2-relevance-experiment.mts`。

### 择优结论

**方案 a（启发式）常开为机械基线；方案 b 以"综合调用同 JSON 融合 verdict"
的形态列为后续增强**——综合调用本就存在（无新增付费调用，budget/stop 守卫
天然满足）：模型按需输出逐来源 verdict+basis 时覆盖启发式判定（可解释），
但机械底线不可被模型自评翻转（无 positively-relevant 来源且无带 basis 的
逐来源判定 ⇒ insufficient；#697 溯源律先例）。理由：①黄金集上门级判定
5/5，零 relevant 假阳性；②确定性纯函数是 TDD 矩阵的可测底座（模型在场与
否门行为不变）；③pi 不可用时（离线/欠费/超时）门保持全功能。

## StageOutcome 与迁移

- `rt-core/src/scheduler/stage_outcome.ts`：类型 + `parseStageOutputs`
  （StageOutcome 原样 / legacy 显式标注 / 损坏 fail-closed）+
  `migrateLegacyStageOutputs`（v12，与解析同一套逻辑）。
- 迁移（ledger v12，Migration 注册表新增 `run` 数据迁移钩子）：旧行
  `["<artifact>"]` → `execution=executed / sufficiency=unknown` 显式标注，
  原 artifact 整体保留在 `legacy` 字段（不丢数据，篡改检测式断言）。
  v12 编号避开 #742 已占用的 v11（task_control）。
- `recordOutcome`（写产出不改状态）：insufficient/conflicted 停泊前落
  unresolvedClaims——重启后 parked 行上仍可读。

## 充分性门与停条件（机械可测）

| stopReason | 触发 | 动作 |
|---|---|---|
| empty-results | 检索 0 来源 | recordOutcome + failStage（重查一轮）→ 停泊 |
| all-sources-irrelevant | 启发式 0 relevant 且模型无 verdict | 同上 |
| synthesis-unavailable | pi 不在场/综合失败/不可解析 | 同上（检索结果保留为降级底座） |
| model-insufficient | 综合自评 insufficient / 未给出自评 | 同上 |
| model-conflicted | 综合自评 conflicted | 同上（gain=裁决冲突） |
| sufficient-without-relevant-source | 自评 sufficient 但 0 relevant | fail-closed 降级 insufficient |
| no-progress-duplicate-query | 同任务重复检索词 | **parkStage 直停泊**（不付费第二次检索） |

重查带 stated information gain（紧凑一句话，持久化在 outcome）：
`<原查询>（补充：<gain>）`；refinement 条件含 conflicted；重查上限由既有
failStage 重试状态机给出（max_retries=2 → 恰一轮重查，无无限循环）。
连续 2 次低新颖度（novelty≤0.15）→ 任务级无进展旗标 → 仲裁员拒绝生长、
图诚实闭合。

## 汇总覆盖语义

- 标题 = `汇总｜<根问题>`；根问题经 seedTaskContext 注册（导图路径
  tree.root.text；research.start 路径任务标题兜底）。
- 闭合条件放宽为全部非汇总节点终态（complete|parked）——停泊分支不再
  永久阻塞汇总；汇总 deps 只含已完成分支。
- 汇总命题 = 根问题 + 全部分支；outcome.coverage 逐分支 answered/gap
  （机械推导自各分支充分性）；gap 分支显式入 unresolvedClaims。

## 阻尼任务隔离

`lastPrior`（共享标量）→ `taskLastPrior` Map；删除死代码 priorByStage
（其 size 判断是串扰入口之一）。回归钉：交错任务 A 的阻尼演化与单独运行
逐值一致（串行 vs 交错同一例子——评估文档要求的回归）。

## 边界（不做）

EvidenceRecord 存储（#746）、GO 门（#745）、"budget 内问用户" RPC（#743
接线后才有预算通道——本 change 用 park + broadcast 诚实停）。
