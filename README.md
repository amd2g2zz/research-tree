# research-tree

## Collection Invariants (v0.1 alpha)

The coordinator, not a research subagent, owns the live collection stage.
For every formulated query it executes every eligible installed provider and
records a terminal result for every provider/query pair. Successful responses
are archived verbatim under `research_drift/discovery/raw/` before leads are
normalized; the discovery cache is rejected when an archived response is
missing or has a different hash.

The coordinator then captures a bounded, provider-balanced source set and
writes `research_drift/sources/<frame>.json`. A missing or altered captured
page invalidates that manifest. Only after both artifacts are valid does the
Frame enter `aggregating` and emit exactly one Source Aggregator task. The
aggregator's hash-bound semantic clustering, source-quality scoring, and
topic-confidence scoring must validate before the Frame enters `reviewing` and
emits the Source Triager and Source Adversary tasks.
Each captured record preserves `discovered_by` and `discovery_providers`
separately from `capture_provider`: the first two name every search engine
that produced the lead, while the latter names the controlled page extractor.
`summary.origin_coverage` makes the resulting cross-provider union auditable.
Each reviewer can select only a captured page from that Frame's manifest whose
current content hash still matches. Both reviewer roles must complete before an
Extractor, Selector, or Resolver task can be scheduled. `source_acquirer.py`
is a coordinator recovery tool; it does not grant evidence acceptance by
itself.

## Decision closure and chapter topology

Decision-bearing contracts declare `decision_questions`. After recursive
research has reached terminal Frames, a dedicated `decision_synthesizer` must
map each question to evidence, inference, action, unresolved conditions, and
parameter provenance before the run can freeze. Every accepted source also gets
an explicit `cited`, `context_only`, `needs_followup`, or `excluded` disposition;
follow-up requires a real information gap.

After freeze, the orchestrator creates one independent writer task per chapter.
Eight chapters therefore produce eight writer subagents and eight fixed chapter
artifacts. The editor first stages a complete draft, a separate senior-user
reviewer checks its decision chains, and the editor performs the final
`compile-report`. The default artifact remains Markdown; PDF conversion is
explicit only.

`research-tree` 是一个以用户意图为根、以证据驱动递归下降的 deep-research skill。它先把原始问题、否定条件、时间范围、用户材料、交付物和不确定性协商为可执行的需求契约，再把后续证据保存在可审计的研究状态中，而不是把问题粗暴地归类到固定主题树。

当前版本：`0.1.0`（alpha）。默认交付物为 Markdown；只有调用方明确要求时，才应把最终 `report.md` 交给 PDF 导出工具。

## 目录

- [它解决什么问题](#它解决什么问题)
- [安装与 setup](#安装与-setup)
- [五分钟启动](#五分钟启动)
- [递归下降与 DAG](#递归下降与-dag)
- [完整研究生命周期](#完整研究生命周期)
- [搜索、来源和证据](#搜索来源和证据)
- [冻结、写作与问答](#冻结写作与问答)
- [Codex、Claude Code 与 hooks](#codexclaude-code-与-hooks)
- [命令参考](#命令参考)
- [数据、配置与安全](#数据配置与安全)
- [验证与故障排查](#验证与故障排查)
- [Alpha 边界](#alpha-边界)

## 它解决什么问题

用户往往给的是入口、现象或带约束的意图，而不是一个已经可检索的题目。例如：

- “agent 写作很烂”；
- “帮我调查 DeepMind”；
- “我想学习 Python，但不要大学课程”；
- “找最近三年有关深度学习的资料”。

这些输入不能靠一次关键词扩展解决。`research-tree` 先把它们保留为 `IntentProgram`，包含原句、硬/软约束、相对时间对应的 reference time，以及尚未消解的歧义。随后一个 Intent Analyst 在任何建帧或联网前，产出需求契约：区分外部 research、用户材料分析、设计要求、写作要求、验收标准、假设与真正阻塞的澄清问题。比如“根据我提供的材料写实验方案”必须形成材料分析和可行实验方案两个交付目标；只有确实需要外部证据的问题才会成为 research frame。每轮研究再从当前帧的已保存证据中提取认知和信息缺口，只选择一个真正阻塞结论的缺口进入子调用；未选分支保留在 frontier 中，等待反证、新证据或预算变化后再访问。

```text
用户意图 + 约束 + reference time
             |
             v
      Intent contract / 最小澄清
             |
             v
         Research frame（仅外部证据问题）
             |
             v
  已保存来源 -> Evidence -> Cognition
                              |
                              v
                       Information gap
                              |
                 选择至多一个缺口（记录理由）
                              |
                              v
                         Child frame
                              |
                         归约回父帧
```

这不是 BFS：系统不会把所有新发现同时扩张为下一层，也不会将搜索引擎类别当成研究方向。搜索 provider 只是 transport/cost 选择；方向始终来自“原始意图 + 当前证据 + 当前信息缺口”。

## 安装与 setup

### 前提

- Python `>=3.11`
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 一个可写的研究工作区

本仓库是文件夹形式的 skill，不是已发布的 PyPI 包。依赖由 `pyproject.toml` 和 `uv.lock` 固定。`uv sync --locked` 与 `uv run --locked` 会拒绝陈旧或缺失的 lockfile，从而保证可复现的环境。

仓库提供了一个只使用 Python 标准库的 setup 脚本。默认模式只检查环境，不写入任何内容；只有显式传入 `--sync` 时才会由 uv 创建或更新本地虚拟环境。

```powershell
# 在仓库根目录执行
python scripts/setup.py --check
python scripts/setup.py --sync --verify
```

`--verify` 会运行全部单元测试。也可分开执行：

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s scripts -p "test_*.py" -v
```

如果只想供自动化检查使用，可获取机器可读的结果：

```powershell
python scripts/setup.py --json
```

### 设置独立工作区

研究状态、抓取页面、快照和最终报告都会写到 `RESEARCH_WORKSPACE`。未设置该变量时，当前目录会成为工作区。建议使用仓库外的空目录，以免把运行产物混入 skill 代码。

PowerShell：

```powershell
$researchWorkspace = Join-Path $HOME "research-tree-workspaces\deepmind"
New-Item -ItemType Directory -Force -Path $researchWorkspace | Out-Null
$env:RESEARCH_WORKSPACE = (Resolve-Path $researchWorkspace)
```

POSIX shell：

```bash
export RESEARCH_WORKSPACE="$HOME/research-tree-workspaces/deepmind"
mkdir -p "$RESEARCH_WORKSPACE"
```

一个工作区对应一个 live DAG。`engine init` 发现已有 `research_drift/research_state.json` 时会失败；要开始另一项研究，请换一个工作区，而不是覆盖原状态。

## 五分钟启动

下面以“调查 DeepMind”为例。所有命令均在仓库根目录执行，且假定已经设置 `RESEARCH_WORKSPACE`。

### 1. 创建项目空间、登记材料与 IntentProgram

`project init` 创建目录布局、`research_project.json` 和 provider 策略；`engine init` 才创建实际的研究 DAG 和处于 `pending` 状态的意图契约。因此两步都需要执行，且只执行一次。

```powershell
uv run --locked python scripts/project.py init --intent "调查 DeepMind 及其近期研究方向"
uv run --locked python scripts/engine.py init --intent "调查 DeepMind 及其近期研究方向" --reference-time "2026-07-29T00:00:00+00:00" --materials "@materials.json"
```

`--materials` 可选；只要用户提供的文件会影响最终答案、材料分析或设计方案，就应在分析前登记为工作区内已有文件。例如 `materials.json`：

```json
[
  {
    "id": "protocol-note",
    "path": "materials/protocol.md",
    "description": "用户提供的现有实验协议",
    "media_type": "text/markdown"
  }
]
```

路径必须相对于 `RESEARCH_WORKSPACE`，登记时会记录内容 SHA-256、大小与媒体类型。后续契约只能把已登记的同名 id 标为 `provided`；冻结前会再次校验其哈希，并把副本放进快照。因此不能在 writer 阶段临时塞入未登记或已变更的材料。

材料也可以在意图契约仍为 `pending` 或 `needs_clarification` 时补充或替换；这适用于澄清后用户才上传协议、数据字典或约束附件的情况：

```powershell
uv run --locked python scripts/engine.py register-material --material "@material.json"
uv run --locked python scripts/engine.py register-material --material "@replacement-material.json" --replace
```

`material.json` 是一个材料对象，不是列表。契约一旦为 `ready`，登记会被拒绝，必须新建或修订意图运行，不能悄悄改变已规划的输入。当前可直接进入材料分析和 chunk/citation 流程的登记文件仅限 `.md`、`.txt`、`.html`。PDF、DOCX 等文件可以被登记和冻结为 hash-bound 输入，但不会被伪装成已解析文本；若它们是必需的材料分析依据，先经显式提取流程生成工作区内的文本材料，再将该文本材料登记并在契约中说明其用途。

对“最近三年”之类相对时间，调用方应在创建意图时固定 reference time，并把它解释成相对于该时刻的范围。不要在后续检索时悄悄滑动时间窗口。

### 2. 先完成意图契约与需求沟通

新项目不能直接建帧或搜索。`engine next` 会返回 `analyze_intent`，或使用 orchestrator 写出唯一的 `intent_analyst` 任务：

```powershell
uv run --locked python scripts/engine.py next
uv run --locked python scripts/research_orchestrator.py --write
```

Intent Analyst 必须提交一个 `ready` 或 `needs_clarification` 契约，而不是直接写 query plan。契约至少含 `deliverables`，并可分别列出 `research_questions`、`design_requirements`、`writing_requirements`、`acceptance_criteria`、`user_materials`、`clarifying_questions` 和 `research_frames`：

```powershell
uv run --locked python scripts/engine.py analyze-intent --contract "@intent-contract.json"
```

每个需要外部研究的交付物必须绑定到具体的研究帧契约引用，而不是让 writer 从快照中任取研究章节。例如交付物使用 `research_frame_refs: ["measurement-evidence"]`，对应的 `research_frames` 项使用 `contract_ref: "measurement-evidence"`。记录后该绑定会进入运行时帧的 `contract_ref` / `deliverable_ids`，冻结后的该交付章节只接收这些已绑定帧的 research inputs。对新契约应显式填写 `research_frame_refs`；省略时系统只会把它解析为当前声明帧的全集，不能用它表达“没有外部研究”。

```json
{
  "deliverables": [{
    "id": "experiment-plan",
    "kind": "experiment_plan",
    "requires_research": true,
    "research_frame_refs": ["measurement-evidence"]
  }],
  "research_frames": [{
    "contract_ref": "measurement-evidence",
    "focus": "可行测量、对照与判定规则的外部证据",
    "information_gap": "哪些测量与对照可支撑该实验目标"
  }]
}
```

当材料缺失、目标读者/成功标准不明、时间解释会改变结论，或指令相互冲突时，契约必须为 `needs_clarification`，并给出最小的 `blocking` 问题。此状态禁止建帧、discovery 和研究 subagent。记录用户回答后回到 `pending`，再要求修订后的 Intent Analyst：

```powershell
uv run --locked python scripts/engine.py answer-intent --answers "@intent-answers.json"
uv run --locked python scripts/engine.py analyze-intent --contract "@revised-intent-contract.json"
```

只回答部分 blocking 问题会保持 `needs_clarification`，不会提前开始搜索；在所有已列问题都得到回答并由 Intent Analyst 提交修订契约前，状态不会变为 `ready`。

只有 `ready` 且没有 blocking question 的契约才能创建其中声明的 `research_frames` 或接受手动 `bootstrap`。这一步与研究过程中的 clause 级 `engine clarify` 不同：后者只处理已经存在的帧所需的局部歧义。

### 3. 建立第一层研究帧

研究帧不是固定分类。它必须明确当前关注点、缺什么信息、如何区分候选答案、希望得到什么更新，以及可接受的证据标准。

工作区内的 `frames.json` 可以包含：

```json
[
  {
    "focus": "DeepMind 的组织与近期研究方向",
    "information_gap": "官方材料如何描述其当前研究重点与组织边界",
    "discriminator": "官方公告、研究页面或版本明确的原始资料",
    "expected_update": "形成可追溯的公司与研究范围基线",
    "evidence_requirement": "保存的第一方来源"
  }
]
```

```powershell
uv run --locked python scripts/engine.py bootstrap --frames "@frames.json"
```

命令输出中的 `frame_ids` 是后续命令要使用的帧 ID。可随时检查下一步和状态：

```powershell
uv run --locked python scripts/engine.py next
uv run --locked python scripts/engine.py status
```

### 4. 形成查询计划并发现 leads

将 `<frame-id>` 替换为上一步返回的 ID。查询计划可包含 1--32 个对象；每个对象至少有非空 `query`，可选 `max_results`（上限为 10）。

工作区内的 `query-plan.json`：

```json
[
  {"query": "DeepMind official research overview", "max_results": 5},
  {"query": "site:deepmind.google recent research announcement", "max_results": 5}
]
```

```powershell
uv run --locked python scripts/engine.py formulate --frame "<frame-id>" --plan "@query-plan.json"
uv run --locked python scripts/research_orchestrator.py --discover --write
```

第二条命令对当前帧的已存查询计划执行所有合格 provider，归档原始响应、物化有界来源集合，并把 lead 批次写入 `research_drift/discovery/`。它会将 collection 标记为完成；带 `--write` 时此时最多只会写出一个 Source Aggregator 任务，不会提前创建 reviewer、Extractor、Selector 或 Resolver。它不会自动接受 evidence。

### 5. 聚合保存来源，再由评审选择 evidence

正常 discovery 会将候选正文保存到 `research_drift/pages/`，并在 `research_drift/sources/<frame>.json` 中记录每个候选的 `captured`、`failed` 或 `deferred_budget` 状态及内容哈希。接下来不是立即启动 Triager/Adversary，而是先只启动一个 Source Aggregator：

```powershell
uv run --locked python scripts/research_orchestrator.py --write
```

Aggregator 只能读取归档 discovery、source manifest 和保存页面。它按实质主题/主张与上下文进行聚合，而不是按 URL、标题或简单文本相似度去重；每个 captured 页面必须有一个 `primary: true` 的主题归属，跨主题页面可附加到其它 cluster。它为来源填写 authority、directness、traceability、temporal fit、capture completeness、independence 等质量分量，也为主题填写来源质量、交叉佐证、独立性、时间一致性、范围匹配等置信度分量。分数由 service 统一计算，代表来源只决定优先评审，不能删除近重复或矛盾来源。

聚合命令绑定当前 manifest 的 SHA-256，成功后生成 `research_drift/aggregation/<frame>.json` 并将帧改为 `reviewing`：

```powershell
uv run --locked python scripts/engine.py aggregate-sources --frame "<frame-id>" --clusters "@topic-clusters.json" --source-manifest-sha256 "<manifest-sha256>"
```

通过 host adapter 提交时，聚合命令还必须包含 `aggregator_role: "source_aggregator"` 和稳定 `command_id`。之后才会出现 Source Triager 与 Source Adversary；二者都只读聚合后的已保存集合，并各提交一次带 `reviewer_role` 的 `evidence` 命令（可为空列表）。选择低质量或非 representative 来源时必须写 `selection_override_rationale`；保留反例/矛盾而非把它们静默合并。两种 reviewer 都完成之前，不能抽取 cognition。

`source_acquirer.py extract` 是 coordinator 的受控恢复抓取工具，不会修改 DAG，也不会单独让新页面成为可提交 evidence。只有重新纳入当前 source manifest、通过聚合和 reviewer 边界的页面才可接受。`@file` 形式是跨 shell 传递 JSON 的推荐方式，尤其适用于 PowerShell；它只能引用 `RESEARCH_WORKSPACE` 内的文件。

### 6. 抽取、下降与归约

Extractor 对已接受的 evidence 生成带 source span 的 cognitions 和候选 information gaps。质量分量、主题置信度与 assessment confidence 会随 evidence 传入；service 将 cognition 的请求置信度限制在其最强的已评估支持上，不能因多个近重复来源而抬高结论。低质量/低置信度支持必须转化为不确定性或限制。若 gap 依赖同一原子提交中刚生成的 cognition，给 cognition 一个唯一 `proposal_ref`，并在 gap 中使用 `trigger_cognition_refs`；已持久化的 cognition 继续使用 `trigger_cognition_ids`。Branch Selector 从 frontier 中选择至多一个会阻塞当前结论的缺口，并说明为什么它值得下降：

```powershell
uv run --locked python scripts/engine.py descend --frame "<parent-frame-id>" --gap "<gap-id>" --child "@child-frame.json" --rationale "该缺口决定当前主张的适用范围，且现有证据不足以排除相反解释。"
```

子帧到达 `resolved`、`contradicted` 或 `insufficient_evidence` 等终态后，Reducer 将它归约到父帧：

```powershell
uv run --locked python scripts/engine.py return-child --frame "<parent-frame-id>" --child "<child-frame-id>" --rationale "子结论已覆盖父帧的关键区分条件。"
```

不要把 `expand` 当作标准路径。它是兼容快捷方式；真实递归下降应使用 `descend`，以持久化“为什么选择此分支而没有选择其余 frontier”的理由。

## 递归下降与 DAG

### 研究状态

语义上的递归 DAG 是唯一权威状态，保存于：

```text
research_drift/research_state.json
```

其主链必须保持无环：

```text
IntentProgram -> Frame -> Evidence -> Cognition -> InformationGap -> ChildFrame
```

`supports`、`contradicts`、`updates`、`refines` 等语义关系保存在单独的 relation graph，可以有环。这并不与 DAG 冲突：前者记录知识间的比较和时间更新，后者只记录一次递归调用如何从一个帧派生到另一个帧。

### 收敛与剪枝策略

系统使用全局最大深度、最大帧数、每帧最大下降次数、前沿分数边界和低置信度返回阈值来限制成本。限制新的工作不会删除未选的信息缺口：它们保持为 `deferred`，可在新证据到来、预算变化或终态帧重新打开时再访问。

当 top frontier 分数接近时，系统要求 Selector 写出比较性理由，而不是用启发式静默剪枝。这样既防止图无限生长，也不会让搜索范围只会越来越窄。

### 约束、歧义与时间

- 原始用户表述始终是合法检索锚点；后续查询由当前帧、已获证据、信息缺口和继承的 intent clauses 共同生成。
- 否定条件、来源偏好、时态、范围和报告要求以 clauses 持久化，并传递到查询、来源接受和写作阶段。
- 对会显著改变交付类型、材料可用性、时间解释或成功标准的含糊/冲突/缺失输入，Intent Analyst 在建帧前提出最小必要问题；帧已存在后的局部 clause 歧义才由 Clarifier 处理。
- 时间是 claim identity 的一部分。认知记录 asserted/evidence time、事件/发布时间、来源版本和上下文。较新的证据可更新旧认知，但不应抹掉历史结论。
- 所有证据都要有本地内容、内容哈希、来源 locator 和时间字段。捕获的片段不等于“已阅读整个原页面”。

详细数据契约见 [references/contracts.md](references/contracts.md)，算法说明见 [references/algorithm.md](references/algorithm.md)。

## 完整研究生命周期

下表描述推荐的端到端流程。除了专门的 host adapter，worker 不直接写 live DAG；它们返回受限的结构化命令，由 service 原子且幂等地落库。

| 阶段 | 责任角色 | 输入 | 允许结果 |
| --- | --- | --- | --- |
| 初始化 | coordinator | 用户意图、clauses、reference time、可选登记材料 | 项目空间、IntentProgram、pending contract |
| 需求理解 | Intent Analyst | 原始意图、clauses、登记材料、已有用户回答 | ready contract 或最小 blocking questions |
| 澄清 | coordinator / 用户 | blocking questions | 已记录回答，回到 Intent Analyst |
| 规划 | Query Planner | open frame、继承约束 | 有界 query plan |
| 发现 | Discovery executor | 已存 query plan、provider policy | 缓存 leads，非 evidence |
| 获取 | coordinator | lead、provider policy | 已保存页面和 hash-bound source manifest |
| 聚合 | Source Aggregator | 保存页面、source manifest | 主题聚合、去重理由、质量/置信度 assessment |
| 评审 | Source Triager / Source Adversary | aggregation、保存页面 | 有 reviewer role 的 evidence 或空选择 |
| 抽取 | Extractor | 已接受 evidence、aggregation assessment | cited cognitions（置信度受 assessment 上限约束）、候选 gaps、时间更新/反驳关系 |
| 选择 | Branch Selector | frontier、预算、区分条件 | 至多一次 `descend` 或返回理由 |
| 归约 | Reducer / Resolver | 子帧终态、父帧 contract | 父帧终态或重新激活的 frontier |
| 冻结 | Publisher | 无 active frames 的 live DAG、材料与 aggregation 审计 | hash 校验的 state、pages、materials、aggregation、corpus |
| 写作 | Writer（每章一个） | frozen snapshot 的章节任务、assessment、交付要求 | 有引用 chunk ID 的研究章或材料/设计交付章 |
| 统稿 | Editor | 所有已验证章节、quality/delivery review | `report.md` 或 repair task |
| 问答 | 专用 Q&A worker | frozen corpus、用户问题 | 只基于冻结证据的答案 |

可将当前研究任务批次写到工作区，供外部协调器读取：

```powershell
uv run --locked python scripts/research_orchestrator.py --write
```

如果查询计划已形成，同时执行发现：

```powershell
uv run --locked python scripts/research_orchestrator.py --discover --write
```

该模块负责 preflight 任务规划、coordinator discovery/materialisation，以及后续角色受限任务规划；它不让 worker 直接改写 DAG。LangGraph 是可选执行控制器：生产环境必须注入持久 checkpointer；它不保存第二份 DAG，也不替代 service 的幂等命令边界。实际 worker 创建由宿主或调用方负责。Provider policy 中的 `max_parallel` 只限制 discovery provider；冻结 writer batch 的 `max_parallel` 独立等于当批 ready chapter task 数。章节依赖未完成时，该章节会出现在 `deferred_chapters` 而不会被提前派发，下一轮依赖 ready 后仍由它自己的 writer task 执行。

## 搜索、来源和证据

### Provider policy

首次执行 `project init` 会创建工作区内的 `research_providers.json`。它控制费用、anti-bot 风险和并行度，但**不**决定研究语义方向。当前默认可执行的 provider 如下：

| Provider | 默认状态 | 用途 | 备注 |
| --- | --- | --- |
| AnySearch | 启用 | discovery、受控 extract | 匿名可用；可选 API key 提高额度 |
| OpenAlex | 启用 | 文献 discovery、metadata | 只产生 lead |
| Crossref | 启用 | metadata、verification | 只产生 lead |
| arXiv | 启用 | 论文 discovery、full text lead | 需保存版本明确的内容后才可引用 |
| GitHub | 启用 | discovery、verification | 只产生 lead |
| DDG / Brave / Exa | 配置模板中默认关闭 | 未来/策略占位 | 当前 discovery executor 不执行它们 |

查看有效策略：

```powershell
uv run --locked python scripts/providers.py eligible
```

如果允许付费或高风险 provider，应由调用方审查并编辑工作区的策略文件；不要通过改变 provider 来绕过用户的意图约束。

### 多 provider 发现与正文 capture 的区别

`discovery_providers` / `discovered_by` 表示哪些搜索引擎产生了一个 lead；`capture_provider` 表示哪个受控 transport 保存了内容。两者不能混为一谈。默认流程会对所有启用 provider 运行 discovery；arXiv、OpenAlex、Crossref 若返回足够实质的摘要或元数据，会走其原生 capture 并明确标为 `metadata_limited`、`full_text: false`，绝不冒充完整正文；短或缺失的原生内容才回退到 AnySearch 页面抽取。因此 `capture_provider` 既不能推断发现来源彼此独立，也不能单独证明内容完整性。`summary.origin_coverage` 会分别记录 candidate/captured/failed/deferred 的发现来源和 capture transport。

### AnySearch

AnySearch 的 discovery 与 extract 都只访问固定 API。默认匿名请求；如调用方已自行配置较高额度，可在当前进程设置 `ANYSEARCH_API_KEY`：

```powershell
$env:ANYSEARCH_API_KEY = "<optional-key>"
```

skill 不读取自己的 `.env`，也不会保存这个 key 或任何 API 返回的 key。extract 只接受公开 HTTPS URL，拒绝本地地址、带凭据 URL 和不受支持的端口。提取内容上限为 50,000 个字符；刚好达到边界时会标为 `possibly_truncated`，只能支持保存内容中的具体 locator，不能声称完整阅读了原页。

### arXiv 与时间敏感研究

```powershell
uv run --locked python scripts/arxiv.py search --query "agent writing" --sort submitted --max 10
uv run --locked python scripts/arxiv.py semantic --id "1706.03762v7" --relation citations --limit 20
```

这些命令返回版本化论文 metadata/citation leads，仍不是 evidence。可选的 Semantic Scholar enrichment 只从进程环境读取 `SEMANTIC_SCHOLAR_API_KEY`。对于“有效/无效/再次有效”这类随时间改变的主题，报告必须保留主张的上下文、时间与版本，而不是合并为没有时间语义的单一结论。

## 冻结、写作与问答

研究未结束时不得开始正式写作或问答。只有完成所有 active frames、通过时间/发布审计并冻结后，章节 Writer、Editor 和 Q&A worker 才可以运行。

### 1. 冻结

```powershell
uv run --locked python scripts/project.py audit-evidence
uv run --locked python scripts/project.py freeze --snapshot "deepmind-2026"
```

`project freeze` 会重新审计 live evidence、时间字段、已完成 aggregation 与登记材料；复制接受的页面、材料和 aggregation artifact，构建 chunk corpus 与倒排索引，并为 state/corpus/materials/aggregation 写入 SHA-256 manifest。冻结快照位于：

```text
research_snapshots/deepmind-2026/
```

`engine.py freeze` 不是完整交付冻结的替代品；发布前请使用 `project.py freeze`。

对 `required && requires_research` 的交付物，冻结还会验证其 `research_frame_refs` 所绑定的帧至少有一个终态且含有带定位引用的 cognition。绑定缺失、未终态或没有已引用的 research input 都会阻止冻结；这确保“实验方案”之类的交付物不会在没有实际研究输入时进入写作阶段。

### 2. 章节与报告

```powershell
uv run --locked python scripts/project.py chapter-plan --snapshot "deepmind-2026"
uv run --locked python scripts/research_orchestrator.py --snapshot "deepmind-2026" --write
```

每个 writer 只接收一个章任务，并只能使用该任务允许的 frozen chunk。章节数就是 writer subagent 数：例如 chapter plan 有 8 个章节，orchestrator 会一次产出 8 个独立的 `writer:<chapter-id>` 任务和 8 个固定输出文件；不会让一个 writer 负责多个章节。宿主可以受自身资源配额限制排队执行，但不能合并章节责任。

除研究帧章节外，ready intent contract 中要求材料分析或设计的 deliverable 会生成独立的交付章节，例如实验方案。它的任务同时带有 frozen material inputs、research evidence inputs、设计要求、验收标准和假设；writer 必须真正产出该交付物，不能用泛泛 research summary 替代。

每个章任务还绑定聚合后的 source-quality、topic-confidence、assessment confidence 以及低分来源/主题的 disclosure 要求。writer 必须让结论强度匹配这些指标，明确材料观察、引用研究、假设和拟议设计的边界。完成后由宿主通过固定输出边界提交：

```powershell
uv run --locked python scripts/host_adapter.py submit-chapter --host codex --snapshot "deepmind-2026" --chapter "<chapter-id>" --content "@research/chapters/<chapter-id>.md"
```

全部计划章节已通过验证后，Editor 才能合成报告。对于普通研究报告，Editor 可直接编译。对于含 `decision_synthesis` 的决策型报告，流程固定为：Editor 先 stage 一份完整 draft，独立的 senior-user reviewer 提交 hash 绑定审查，最后仍由 Editor 编译同一份已审 draft。reviewer 只审查，不替代任何 writer，也不接管统稿。

```powershell
# 决策型报告：editor 先写 draft，再由独立 reviewer 审查，最后 editor 编译
uv run --locked python scripts/host_adapter.py stage-report --host codex --snapshot "deepmind-2026" --content "@research/editor/report_draft.md"
uv run --locked python scripts/host_adapter.py submit-report-review --host codex --snapshot "deepmind-2026" --content "@research/editor/report_draft.md" --assessment "@research/editor/report_review.json"
uv run --locked python scripts/host_adapter.py compile-report --host codex --snapshot "deepmind-2026" --content "@research/editor/report_draft.md"
```

Editor packet 会再次审查 citation、低分 disclosure、质量上限及材料/设计交付要求；发现 unsupported、过度自信或未满足的交付要求时必须返回 repair task。

`intent_deliverable` 章节还带有 `delivery_checklist` 与 `input_use_requirements`。writer 必须在正文相应位置放入每项的机器可审计覆盖标记，例如：

```markdown
<!-- research-tree:check design-1 -->
<!-- research-tree:check acceptance-1 -->
<!-- research-tree:check material-protocol-note -->
<!-- research-tree:check research-chapter-f_0001_example -->
```

标记只证明作者显式声明已处理该义务，不能替代 editor 对正文的语义审查。对有可引用 chunk 的必需材料和绑定 research input，章节还必须至少引用该输入允许的一个 frozen `chunk_id`；只有无可引用 chunk 的受限输入可以仅用标记并说明限制。`submit-chapter` 会拒绝遗漏标记或必需输入引用的章节，`compile-report` 会再次校验，因此缺少交付检查不能被统稿阶段悄悄带过。这里的写作检查发生在冻结之后；冻结前的对应门禁是上述 research-frame 绑定与已引用终态输入审计。

输出为工作区根目录的 `report.md`，并带有 `research/editor/report_manifest.json`。报告与章节引用的 `c_<id>` 必须属于冻结快照允许的 corpus；不支持的主张应返回 repair task，而不是编造衔接性文字。

默认只发布 Markdown。用户明确要求 PDF 时，调用方可将已验证的 `report.md` 交给兼容的导出器（例如 any2pdf）；`research-tree` 不会自动触发 PDF 生成。

### 3. 冻结后的问答

```powershell
uv run --locked python scripts/qa.py ask --snapshot "deepmind-2026" --question "近期研究方向有什么变化？"
```

该命令只检索快照内的 corpus，返回 evidence packets、快照 reference time 和 frozen time。Q&A worker 必须引用 `chunk_id` 与 `source_path`，证据不足时回答 partial/unknown，不能重新搜索或修改 live DAG。

## Codex、Claude Code 与 hooks

`host_adapter.py` 是 file-protocol 边界，当前只支持 `codex` 和 `claude-code` 两个宿主名称。它不会替宿主创建 subagent 或执行 worker 给出的任意 shell 命令。

```powershell
# 写入 Codex 可读取的 live worker batch，并可选地执行 lead discovery
uv run --locked python scripts/host_adapter.py dispatch --host codex --discover

# 保存一个公开页面，但不修改 DAG
uv run --locked python scripts/host_adapter.py acquire-source --host codex --url "https://example.com/source"

# 仅在 frozen snapshot 上生成 Q&A task
uv run --locked python scripts/host_adapter.py dispatch --host claude-code --snapshot "deepmind-2026" --question "近期有什么变化？"
```

`dispatch` 将任务写入：

```text
research/orchestrator/<host>/worker_batch.json
```

worker 只能把已验证的结构化命令列表交回 `submit`；每条命令需要稳定的 `command_id`，service 会把重放处理为幂等操作。

### 可选 hook

以下模板必须**手动合并**到宿主的本地配置，不能直接覆盖已有设置：

| 宿主 | 模板 | 合并目标 |
| --- | --- | --- |
| Claude Code | `hooks/claude-code.settings.template.json` | `.claude/settings.json` |
| Codex | `hooks/codex.hooks.template.json` | `.codex/hooks.json` |

hooks 只记录最小生命周期事件和只读任务摘要；它们不会自动搜索、派发 worker、提交命令或绕过宿主权限。它们适用于从本 checkout 启动的宿主，并要求 `RESEARCH_WORKSPACE` 保持在该 checkout 内。

更多限制见 [references/hooks.md](references/hooks.md)。

## 命令参考

| 脚本 | 主要子命令 | 用途 |
| --- | --- | --- |
| `scripts/setup.py` | `--sync`, `--verify`, `--json` | 检查环境、同步 locked 依赖、运行测试 |
| `scripts/project.py` | `init`, `audit-evidence`, `freeze`, `chapter-plan`, `editor-packet`, `submit-chapter`, `stage-report`, `submit-report-review`, `compile-report` | 项目空间、冻结和交付边界 |
| `scripts/engine.py` | `init`, `analyze-intent`, `answer-intent`, `register-material`, `bootstrap`, `formulate`, `aggregate-sources`, `evidence`, `extract`, `synthesize-decision`, `descend`, `return-child`, `finish`, `reopen`, `clarify`, `next`, `status`, `time-audit`, `export` | live recursive DAG 的唯一 CLI 写入边界 |
| `scripts/research_orchestrator.py` | `--discover`, `--refresh-discovery`, `--write`, `--snapshot`, `--question` | 生成角色任务、缓存 discovery 或规划冻结任务 |
| `scripts/source_acquirer.py` | `extract` | 保存受控 AnySearch extract，返回 evidence proposal |
| `scripts/providers.py` | `init`, `status`, `eligible` | 检查 provider 策略 |
| `scripts/corpus.py` | `build`, `search` | 构建或查询 live 本地语料；正式交付优先用 frozen corpus |
| `scripts/qa.py` | `ask` | 检索 frozen snapshot 的证据包 |
| `scripts/host_adapter.py` | `dispatch`, `submit`, `acquire-source`, `submit-chapter`, `stage-report`, `submit-report-review`, `compile-report`, `answer` | Codex/Claude Code 的受限 hand-off |
| `scripts/arxiv.py` | `search`, `semantic` | 版本化论文和 citation lead discovery |

所有 CLI 输出均为 JSON，适合由协调器读取。涉及 JSON 的参数可直接传 JSON 文本，或传 `@relative-file.json`；后者始终相对于 `RESEARCH_WORKSPACE`，并受到工作区边界检查。

## 数据、配置与安全

首次初始化后，典型工作区如下：

```text
research_project.json                 # 交付默认值与布局
research_providers.json               # provider 成本/风险/并行策略
research_drift/
  research_state.json                 # live semantic DAG
  pages/                              # 已保存来源内容
  discovery/                          # 可缓存但不可引用的 leads
  sources/                            # hash-bound captured/failed/deferred manifest
  aggregation/                        # topic de-duplication and quality/confidence artifacts
research_corpus/                      # live chunk/vector/inverted index
research_snapshots/<snapshot-id>/     # hash 校验的冻结 state、pages、materials、aggregation、corpus
research/
  orchestrator/                       # worker batches
  chapters/                           # 已提交章节
  editor/                             # editor packet 与报告 manifest
report.md                             # 默认最终交付物
```

安全与完整性原则：

- URL、摘要、搜索结果和 metadata 都是 lead，不能直接支持 cognition 或报告事实。
- evidence 必须对应本地保存内容，并在冻结时重新校验哈希。
- 任何 `possibly_truncated` capture 只支持其保存片段；不可据此得出“网页整体如此表述”的结论。
- API key 只能从进程环境读取，不能提交进 `.env`、任务包、快照或报告。
- worker 不可提供任意目标路径或任意命令给宿主执行；输出路径和引用集合由 service/frozen snapshot 重新验证。
- 使用独立、最小权限的工作区。不要把包含凭据的目录设为 `RESEARCH_WORKSPACE`。

## 验证与故障排查

完整验证：

```powershell
python scripts/setup.py --sync --verify
uv lock --check
```

常见问题：

| 现象 | 原因与处理 |
| --- | --- |
| `research state already exists` | 当前工作区已有 live DAG；切换到新的 `RESEARCH_WORKSPACE`。 |
| `Q&A is available only for a frozen snapshot` | live research 尚未完成；完成 active frame 并运行 `project.py freeze`。 |
| `cannot compile report; missing submitted chapters` | 每个 chapter task 都要先通过 `submit-chapter`。 |
| `frozen snapshot integrity check failed` | 快照中的 state/corpus/page 哈希不匹配；不要修改冻结目录，重新审计并冻结新的 snapshot。 |
| lead 为空或 provider 失败 | 检查 query plan、网络和 `research_providers.json`；失败会被记录，不应静默缩窄方向。 |
| AnySearch extract 被拒绝 | 仅支持公开 HTTPS URL；不要传 localhost、私网、带凭据 URL 或非标准端口。 |
| `@file` 参数失败 | 确认文件在 `RESEARCH_WORKSPACE` 内，且 JSON 根类型符合命令要求。 |

## Alpha 边界

- 当前仓库提供研究状态、检索/证据边界、任务规划和宿主适配；实际 subagent 的创建、模型选择和长期持久 checkpointer 由调用方注入。
- 默认向量是确定性的 feature hashing，并结合倒排索引；生产环境可替换为 embedding provider，但应保留现有 JSONL/index 契约。
- 只有 AnySearch、OpenAlex、Crossref、arXiv 和 GitHub 已接入 discovery executor。配置文件里出现的其他 provider 不代表当前可执行。
- PDF 是显式的后处理，不是默认或自动交付。
- Alpha 阶段建议在隔离工作区试运行，并先完成完整测试与一次冻结/交付演练后再用于重要研究。
