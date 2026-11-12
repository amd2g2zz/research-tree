# 架构规格 — research-tree v2.0

版本 v2.3 · 2026-10-30（v2.3：**数据源插件接口**——执行层新增 `DataSourceProvider` 端口，检索类数据源可插拔，默认集成 anysearch，飞书等以适配器接入；v2.2：语言裁定——v2 引擎全量 TypeScript，rt-core 为引擎本体，Python v1 冻结为遗留参照；v2.1：产品层补齐项目首页/研究树侧栏/快照视图/hub 对话（原型回写）；v2.0：git 语义对象模型落架构——Project/Task/Version/Fork/Draft 存储、内容寻址提交、分叉图谱、主分支投影；产品状态机改为三步走；v1.1 阶段 DAG/Kùzu/画布 server 保留）

## 四层架构

```
┌ 产品层 ─────────────────────────────────────────────────┐
│ Skill 入口（产品语言）· CLI（headless，--json）          │
│ **项目首页**(应用默认落点=默认项目概览)                   │
│ **侧栏研究树**(项目→任务→版本/草稿三层导航,可折叠)        │
│ **项目空间**: 建项目(附件)→chat(task-id)→分解确认→研究    │
│ **版本时间线**(主分支默认投影/分叉边/切换) · 报告/底稿渲染 │
│ **快照视图**(任意已提交版本只读投影) · hub 对话(主界面)   │
├ 引擎层（新建核心件 = run-plan 解释器）────────────────────┤
│ 产品状态机 v2.0: CHAT→(确认)DECOMPOSE→(签署)RESEARCH⟲    │
│   (EVSI→验证→早终止硬门→偏航检查)→CONVERGED(产物可删,    │
│   未冻结)→(冻结)COMMIT[vN hash+摘要]→CHAT(继承对齐)→     │
│   RESEARCH[vN+1]… ；fork(v)=(新task,继承快照,fork_edge)  │
│ A0 六要素分解 · A1-A6 + 贝叶斯证据引擎 L1-L5 + Thompson   │
│ **阶段 DAG 调度器**（递归/开环/12h 硬帽）· 项目管理器      │
│ **canvas server**（WebSocket 投影+五写门）                 │
│ 偏好防火墙: 偏好字段物理不可达推理层                      │
├ 执行层 ─────────────────────────────────────────────────┤
│ workers（检索/代码阅读/实验）· 原告/辩护对抗子代理        │
│ 验证子代理（fresh-context 盲重推导）· 实验执行子代理      │
│ （设计者不执行）· 证据存储（内容寻址 sha256）             │
│ **subagent 派发（v2.3）**：基于 pi 官方目录的 pi-subagents │
│   扩展（隔离会话/并行/自定义 agent 类型）；rt-core 只做    │
│   4 类 worker→agent-type 映射与派发策略（≤4 并发/盲验）    │
│ **数据源插件接口（v2.3）**：DataSourceProvider 端口        │
│   search(query)→结果 · fetch(ref)→文档 · capabilities()    │
│   具名 provider 注册表（配置驱动选择）；**默认 anysearch**  │
│   飞书/Lark·数据库·内网 wiki 等以适配器接入；每次检索动作   │
│   落事件流（provider 身份进搜索信封，可审计可重放）；密钥    │
│   注入式配置，永不入账本                                   │
├ 持久与部署层 ────────────────────────────────────────────┤
│ SQLite coordinator（单权威，已有）· turn-records          │
│ **版本存储**: versions/commits/fork_edges（append-only,  │
│   快照=要素集+账本+证据引用+报告+deleted_nodes 整体哈希） │
│ **draft 存储**: 工作态（无 hash 不入图谱，可变）          │
│ 账本/假设/意图 版本化 store · Kùzu 对象图（含 fork 血缘）  │
│ 部署形态: ①pi 原生应用（独占宿主，v2.3）②引擎独立进程     │
│ ③loopx goal adapter（I1-I7，G1-G5 增益达标线）           │
│ ④DSH 深度适配（goal/deliverables/guard/subagent-fork/SDK │
│ 全用原生包；绕开原生包自建=适配失败）                    │
└────────────────────────────────────────────────────────┘
```

## 对象与存储模型（v2.0 核心）

```
projects(project_id PK, topic, created_at, attachments JSON)     # project_id 隐匿生成
tasks(task_id PK, project_id FK, parent_fork FK→fork_edges|NULL, created_at)
versions(task_id FK, v, commit_hash UNIQUE, parent_v, verdict,
         summary, snapshot_ref, deleted_nodes JSON, created_at)  # append-only
fork_edges(from_task, from_v, to_task)                           # 图谱血缘边
drafts(task_id PK, working_set_ref)                              # 未冻结工作态，无 hash
```

- **快照 = commit 的全部语义**：`commit_hash = sha256(要素集 ‖ 账本 ‖ 证据引用表 ‖ 报告 ‖ deleted_nodes)`；部分提交不存在（A7 规则 1）。
- **Kùzu 对象图**节点/边扩展：`VersionNode`（含 verdict/hash）、`FORKED_FROM` 边——分叉血缘是一等图查询（"我从哪来"与"我派生了谁"双向 O(1)）。
- **主分支投影**：`main_task(project_id)` = 无 parent_fork 的 task；默认渲染其最新 version 的快照投影。切换 = 显式 (task_id, v) 寻址。
- **draft 与 version 的边界**是唯一写入口：所有写操作发生在 draft；`freeze()` 是唯一 draft→version 通道（fail-closed，无旁路）。

## LLM / 算法分工（rigor 落点）

| LLM（产出判断，落盘为数据） | 算法（在数据上机械裁决） |
|---|---|
| **六要素分解提取（A0，溯源校验过才落盘）** | **充分性 checklist、溯源律校验** |
| 段落四分、主张提取（schema 校验过才入账） | 收敛判定、追问选择、EVSI 排序 |
| kill 图边与权重提议 | 中心性、make-or-break 判定、**kill 硬门** |
| 证据检索、实验设计、变体候选 | 后验计算、裁决规则、早终止触发 |
| **版本摘要消息生成** | **commit 快照哈希、fork 血缘记录** |
| 报告叙事文字 | 底稿纯投影；双交付物同源一致 |

## 新旧映射（诚实账 · v2.2 语言裁定后）

**裁定（2026-10-30，用户）**：v2 引擎**全量 TypeScript**——存储、账本、算法、状态机、调度、headless、MCP 全部在 rt-core（TS，pi 原生扩展承载）。既有 Python v1（beta1/beta2，~1770 tests）**冻结为遗留产品**：不再接收 v2 工作，其价值从"代码复用"改为**语义与测试规格复用**——下列组件的机械规则、schema 与验收用例是 rt-core 实现的参照系，通过后由 vitest 重新钉死。bash bridge 取消（原 T0 规划的临时缝不再需要）。

| v2.0 组件（rt-core TS） | Python v1 参照（语义规格） | 性质 |
|---|---|---|
| 槽位/意图模型 | decision_frame.py | 语义复用，TS 重写 |
| 六要素分解 A0 | —（beta1 brief_refinery.py 提取语义可参照） | 新算法件，TS |
| 主张账本/kill 图 | claims.py + contradictions.py | 语义复用，TS 重写 |
| 溯源/证据引擎 | origins.py / finding packs / sha256 receipts | 语义复用，TS 重写 |
| 连续性 | turn-records fail-closed（#497） | 语义复用，TS 重写 |
| 引擎底座 | coordinator（SQLite） | **schema 语义复用，TS 重写**（better-sqlite3） |
| 版本/分叉 A7 | — | 新算法件，TS（kuzu npm） |
| 调度 | — | 新算法件，TS |
| 早终止 | —（研究必须跑完是产品缺陷） | 新算法件，TS |
| pi 宿主（extension/subagent 池/会话树） | host_capabilities.py（pi 席位语义） | rt-core 本体 |

结论：约 55% 的复用从"既有零件表面化与编排化"转为**规格复用**；真正新算法不变（收敛判定、EVSI 统一选择、kill 图/变体搜索、证据引擎 L1/L2、六要素分解、版本快照/分叉）——全部是"账本上的机械规则"，零 prompt 玄学。双栈并存期：遗留 Python 包（`src/research_tree`）保持可安装可测试直至 v2.0 发版退役（退役机制随 release 流程单独定）。

## 数据源插件接口（v2.3，执行层端口）

**动机**：研究的事实来源必须可插拔——通用搜索接 anysearch（默认），JS 重渲染页接 **agent-browser**（第二个内置适配器），企业数据接飞书/Lark 文档、数据库、内网 wiki 等。检索能力是 provider 的，审计与裁决语义是引擎的。

**插件清单与惰性披露（v2.3）**：provider 全文用量指南**不进 context**——注册表只持轻量清单（name / capabilities / kinds / 一句话描述 / usage 指针），引擎提供 `providers.search(capability|keyword)` 按需检索，**选中的 provider 才加载完整 usage**（先例：agent-browser 的 discovery-stub 模式——stub 只是指针，`skills get core` 按需取全文；#501 两层契约：引擎管结构门，行为面按需装配）。任何时刻进 context 的 provider 全文 ≤ 选中数，未选中者只有清单行。

**setup 与 boot（v2.3）**：`rt setup`（幂等）+ `rt doctor`：extension 注册进 pi、provider CLI 依赖检查与安装指引（anysearch/agent-browser，版本 pin）、workspace 初始化（ledger/图投影库）、boot readiness 报告（各 provider 可用性、存储可写、MCP 挂载、pi 会话）。安装不静默：全局安装与凭据写入先报告再执行。

**内置适配器（T0 交付三个）**：
- `anysearch`（默认）：通用 web 搜索（kinds: web-search）。
- `agent-browser`：浏览器渲染抓取（kinds: web-rendered）——经 agent-browser CLI（Rust+CDP，无 Playwright 依赖）的 `read <url>` 抽取 agent 可读全文、`open`+snapshot 处理需交互/登录态页面；anysearch 结果里的 JS 重渲染页由 EVSI/成本路由到它。CI/无人值守环境用 headless Chromium。
- `web_fetch`：直连抓取与文档转换（kinds: web-page / pdf / office-doc）——HTTP GET + 正文抽取（@mozilla/readability + turndown，本地免费）转 markdown；**pdf/pptx/docx/xlsx → markdown 复用 markitdown CLI**（Microsoft 开源，MIT，本地运行，#588 provisioning）；纯文本/代码资源保留原文并附**确定性摘要**（标题/节结构/代码块清单/行数/语言探测——非 LLM，provider 层零模型调用）。路由：静态资源走 web_fetch（快、省），JS 重渲染走 agent-browser。全栈本地开源免费，零付费 API。

```
DataSourceProvider（rt-core 端口，src/providers/）
  capabilities(): { search: bool, fetch: bool, kinds: ["web","lark-doc","db",…] }
  search(query):  SearchQuery → SearchResult[]   # 标题/URL或源内地址/摘要/原始引用
  fetch(ref):     ResourceRef  → Document        # 全文抽取（内容寻址后进证据存储）
```

- **注册表**：具名 provider（配置驱动选择；run 级/任务级可覆盖）。**默认 anysearch**——v1 已 vendored anysearch-skill v2.1.0（pin SHA，见 skill_setup.py），v2 将其 CLI 语义包成首个适配器；飞书/Lark 等后续适配器同接口接入，引擎零改动。
- **审计即事件**：每次 search/fetch 动作落事件流（provider 名、query、结果数、选中引用），A4 搜索信封（查了什么/没查什么）直接由事件流投影——换 provider 不改变审计语义。
- **证据接入**：fetch 回的 Document 经内容寻址（sha256）进证据存储，挂 evidence.upsert 事件；来源可靠性后验（L1）按 provider 维护。
- **密钥边界**：provider 凭据注入式传入（env/config），永不落账本与事件流。
- **与 A0 附件的边界**：DataSource 是 pull 型（引擎主动检索）；用户上传附件是 push 型，归 A0 背景要素解析（#549），不混用本端口。
- **EVSI 对接**：A3 动作选择里的"再读独立源"成本含 provider 配额/延迟画像（capabilities 携带），多 provider 时按 EVSI/成本选择。

## 存储扩展（coordinator schema 增量）

```
claims: + posterior REAL, + verify_tier, + kill_edges JSON, + incentive_flag, + deleted_at（产物删除，随快照入版本）
sources: 新表（reliability 后验、激励向量、协同标记、溯源边）
hypotheses: 新表（假设账本：候选方案、评审结果、同台对比）
directions: 新表（臂价值后验、预算分配、轮次历史）
experiments: 新表（预注册 payload、序贯停止状态、成本实耗）
decompositions: 新表（六要素集 + 溯源引用 + checklist 状态；随版本快照落盘）
versions/fork_edges/drafts: 见对象与存储模型
```

## 递归阶段化（v1.1 增量，保留）

Stage=kill 图因子簇；开环=已决∥EVSI 饱和∥预算尽→ROLLUP+信念传播；不满足→因子化下钻（LLM 因子化+kill 图挂边）；异构 worker 4 类并行（≤4 并发，任务级重试/阶段级 park）；全局 12h 硬帽→强制收敛+PARK 兜底。Spark 借执行模型直觉（DAG/阶段/lineage）不引入流处理框架——Flink 式下钻=UI lineage walk（画布→抽屉→原始 session/证据）。

## 安全与边界

- 偏好防火墙：推理层接口无偏好参数（架构级信息流控制，非政策提示）。
- 实验反作弊：预注册判据先于执行、设计者≠执行者、成本上限硬门。
- 对抗信息：层级地板+污染封顶；残余风险（高级洗白）在搜索信封披露。
- 认识论边界：rt 不验证一切——experiment-gated 主张如实登记，交下游小流量试点。
- **版本完整性（v2.0）**：freeze() 是 draft→version 唯一通道；已提交版本 append-only；deleted_nodes 随版本披露——研究历史不可被静默改写。

## 治理与 CI（延续 rt 仓库纪律）

one issue one branch one PR；TDD+SDD；GitNexus impact 先行；≤1500 行硬限；引擎算法（收敛判定/EVSI/裁决规则/kill 传播/快照哈希/fork 血缘）全部有单元测试——**机械规则必须被测试钉死，这是"账本不动摇"的工程含义**。rt-core TS 侧质量门：`tsc --noEmit` + vitest 进 CI（随首个 rt-core PR 交付 workflow 变更）；SQLite 驱动 = better-sqlite3，对象图 = kuzu npm 0.11.x（两绑定均已在 macOS x64 / node 24 冒烟验证）。
