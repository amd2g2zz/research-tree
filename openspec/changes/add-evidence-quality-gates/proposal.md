# Proposal: add-evidence-quality-gates

## Why

issue #744（P0，ISSUE-004/006）：检索执行成功、来源相关、证据充分、"得到可用发现"
这四个事实在产品里被压缩成一个 `complete`——综合失败仍无条件 `completeStage`
（`research_worker.ts:346-384`），增益只喂阻尼不阻塞完成（:398-420），全部节点
complete 后注册的汇总节点标题取第一个分支文本（`closeGraphIfComplete`：
"汇总｜限制条件"，ISSUE-006）。dogfood 实证：医院病历摘要任务的"探索｜任务背景"
节点收到游戏剧情/太空探索/航天路线图/背景音五条来源仍 complete，随后自动汇总。

`docs/evaluation/2026-11-19-reverse-engineering-evidence-and-learning.md` 指出三处
信号失真（SDD 输入）：

1. **增益信号失真**（§ 当前优化信号在哪里失真 1）：模型自评相关度/覆盖度 ×
   bigram novelty 合成后验——同一原始证据的改写与独立原件的同义结论可能得到
   颠倒排序。自评标量不能替代逐来源的相关性判定（verdict + basis）。
2. **阻尼基准跨任务串扰**（同节 2）：`updateGain` 用 runner 共享的 `lastPrior`
   作比较基准，且用 `priorByStage.size` 判断"是否有先验"——任一任务登记过
   先验后，另一任务的更新就会改变本任务的阻尼比值。多任务并发下增益抑制
   互相污染。
3. **完成语义混淆**（同节 3）：综合失败后保存原始结果并 `completeStage`——
   "保存成功、证据足够、导图问题已回答"三个各有用途的事实必须分别可读，
   训练与 GO 都需要分别读取。

## What Changes

1. **StageOutcome 结构化**：`parallel_stages.outputs` 从裸 artifact JSON 换成
   结构化四态（execution 执行 / relevance 逐来源 verdict+basis / sufficiency
   充分性 / unresolvedClaims 显式未决 + findings 引用）。迁移：旧行 →
   `execution=executed`、`sufficiency=unknown` 显式标注，原 artifact 整体保留
   在 `legacy` 字段（不丢数据）。
2. **充分性门**：`completeStage` 仅当 sufficiency ∈ {sufficient}。全部来源
   不相关 / 空结果 / 冲突 / 综合不可用 → insufficient/conflicted ≠ 完成。
   insufficient → 带 stated information gain 的重查（一轮，复用既有
   failStage 重试/停泊状态机）→ 仍不足 → parked + 显式 unresolvedClaims。
   综合失败 ≠ 完成。
3. **无进展停**：机械停条件——同任务内重复检索词（无 stated gain 的重复查询）
   直接停泊不再付费检索；连续近重复发现（bigram novelty ≤ 阈值）触发任务级
   无进展旗标，仲裁员停止生长、图按当前状态诚实闭合。
4. **汇总覆盖语义**：汇总节点标题 = `汇总｜<根问题>`（不再取第一个分支文本）；
   仲裁 prompt 的"整体研究问题"同样用根问题；汇总产出记录逐分支覆盖
   （answered/gap）。根问题在 research.start/confirm 时经 seedBranches（现死
   代码，复活为任务上下文注册）传入 runner。
5. **阻尼基准任务隔离**：`lastPrior` 与先验判断改为 per-task
   Map，交错任务互不污染（evaluation 文档失真 2 的修复）。
6. **相关性判定（E2 实验择优）**：启发式打分（查询/来源 bigram 重叠，纯函数、
   零调用成本、确定性可测）为常开基线；综合调用在同一 JSON 里按需输出
   逐来源 verdict+basis（无新增付费调用）时覆盖启发式（带 basis 可解释）。
   充分性门本身保持机械可测（全不相关 ⇒ insufficient，模型不可信其自评
   翻门）。E2 黄金集实验数据见 design.md。

## Impact

- `rt-core/src/scheduler/stage_outcome.ts`（新）：StageOutcome 类型 +
  `parseStageOutputs`（读时归一化 legacy → 结构化，fail-closed 到 unknown）。
- `rt-core/src/scheduler/parallel_dag.ts`：`completeStage` 签名收 StageOutcome；
  新增 `recordOutcome`（写产出不改状态——停泊前显式落 unresolvedClaims）。
- `rt-core/src/store/ledger.ts`：migration v11——重写 parallel_stages.outputs
  旧行为 StageOutcome（显式标注 + legacy 保留）。
- `webui-server/src/research_worker.ts`：execute 的门逻辑（相关性/充分性/
  stated-gain 重查/停泊）、无进展检测、per-task 阻尼、closeGraphIfComplete
  标题与覆盖、seedBranches 复活。
- `webui-server/src/relevance.ts`（新）：启发式相关性纯函数。
- `webui-server/src/server.ts`：research.start / mindmap 确认路径调用
  seedTaskContext（根问题+分支）；画布 projection 读 StageOutcome。
- `webui-server/src/graph_arbiter.ts`：arbiterWave 的问题注入改根问题
  （worker 侧传参，arbiter 文件本身签名不变）。
- 测试：`webui-server/test/research_worker.test.ts` 扩展 + 
  `webui-server/test/fixtures/golden-relevance/`（确定性黄金集）+ 
  `rt-core/test/stage_outcome.test.ts`（迁移/归一化/篡改式断言）。
- 不做（边界）：EvidenceRecord 存储（#746）、GO 门（#745）、"问用户"RPC
  （#743 budget 接线后才有 budget 内问的通道——本 change 用 park+广播诚实停）。

## Non-goals

- 不改 EvidenceEngine / EVSI（仍是未接线资产）。
- 不改 pi-run 控制面（#742/#743 的任务级 stop/预算）。
- 不动 Python 冻结面。
