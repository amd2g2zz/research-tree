## ADDED Requirements

### Requirement: the mindmap is a full-canvas editable tree

思维导图 SHALL 渲染为全画布横向树（root=核心问题，depth-1=限制条件/任务背景/调研目标等，≤5 级），每节点 SHALL 带 quote 溯源引文；draft 态 SHALL 可编辑（rename/addChild/delete）；确认 SHALL 冻结树并从叶子机械派生 stages 注册进 DAG。

#### Scenario: generate → edit → confirm
- **WHEN** mindmap.generate runs on a keyed session then mindmap.confirm confirms
- **THEN** the tree renders full-canvas with quotes, editing works in draft, and confirm walks the task to research phase with stages registered

### Requirement: the research canvas is a full-page DAG view

调研画布 SHALL 为全屏页：阶段卡按依赖深度分列、状态徽章、底部 Console 条、冻结裁决模态。

#### Scenario: research canvas renders stages
- **WHEN** mindmap.confirm registers stages and the user switches to research view
- **THEN** the DAG shows stage cards grouped by dependency depth with status badges

### Requirement: the chat is the hub with view navigation

chat SHALL 为默认视图；顶栏「思维导图」「调研画布」SHALL 切换到对应全屏页（非面板）；「回到对话」SHALL 返回 chat。

#### Scenario: view navigation
- **WHEN** the user clicks 思维导图/调研画布 in the topbar
- **THEN** the corresponding full-screen page replaces the chat view, with a back button to return
