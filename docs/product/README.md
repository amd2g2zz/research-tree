# research-tree 产品文档（v2.1）

> research-tree 是研究台：接住任何清晰度的想法，做一份诚实的、带反证的研究，给出裁决——研究像 git 一样生长：主线 + 支线，版本可追溯、可分叉。

| 文档 | 内容 |
|---|---|
| [00 产品宪章](00-product-charter.md) | 定义、对象模型（Project/Task/Version/Fork/Draft）、三步走、七条设计公理、四结局、差异化定位、三件信任面、验证假设 H1-H7 |
| [01 核心算法](01-core-algorithms.md) | A0 六要素分解 + A1-A6 + A7 版本与分叉 + 贝叶斯证据引擎 L1-L5 + Thompson 方向采样 + 偏航三级恢复 |
| [02 架构](02-architecture.md) | 四层（含版本存储/fork_edges/drafts）、LLM/算法分工、新旧映射、Kùzu 对象图（含 fork 血缘）、安全边界（freeze 唯一通道）、CI 纪律 |
| [03 旅程与体验](03-journey-and-ux.md) | hub 页面逻辑（对话=主界面）、页面清单 P0 首页→P5 版本、六要素分解可视化、三层图谱、报告/底稿双渲染、关键交互件、产品红线 |
| [04 路线图](04-roadmap-v1.md) | T0 引擎+存储骨架（含版本/分叉/分解）→ T1 单闭环+分解可视化+产物管理 → T2 对抗/并行/早终止/12h 无人值守 → T3 项目管理+版本时间线+分叉 → T4 学习层；能力制里程碑 |

**可交互原型**：`/visualizations/rt-studio-prototype/`（React+Vite；`PRD.md` 为其验收来源，与本套件 P0-P5 对应；`?scene=` 可直达各阶段）。原型迭代中验证并回写了本套件：hub 页面逻辑、三层图谱、侧栏研究树、项目首页、快照视图、产物删除（deleted_nodes 随快照）。

**视觉**：ZCode 桌面端 zai-dark 主题令牌（背景 #161616 · 面板 #202020 · 卡片 #2b2b2b · 主按钮白底黑字 · 状态色=终端色）。

状态：v2.3 定稿待评审（2026-10-30：宿主独占——rt 只支持 pi agent，旧 harness 兼容移除，MCP 出口保留；（2026-10-30：**语言裁定——v2 引擎全量 TypeScript**，rt-core 为引擎本体，Python v1 冻结为遗留参照；2026-10-28：git 语义对象模型 + 三步走 + 原型验证回写页面逻辑）· 下一步：T0 引擎+存储骨架（rt-core TS）开工（one-issue-one-PR）
