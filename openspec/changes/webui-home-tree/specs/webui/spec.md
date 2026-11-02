## ADDED Requirements

### Requirement: the sidebar tree renders the three-layer research tree

侧栏 SHALL 渲染 项目→研究线（main ●/fork ⑂）→版本节点（vN·hash·裁决，最新在上，⑂ 已分叉标记）与草稿行（未冻结·不可跟踪）；数据 SHALL 源自 /api/tree 的 #571/#548 只读装配。

#### Scenario: tree shows versions newest-first and the draft row
- **WHEN** a main line has committed v0, holds an unfrozen draft, then commits v1
- **THEN** the tree lists v1, v0 top-down, the draft row disappears after the freeze (freeze consumes it), and fork markers appear where fork edges exist

### Requirement: card wall management with engine red lines verbatim

卡片墙 SHALL 支持归档与删除；未归档删除 SHALL 被引擎拒绝且错误 SHALL 原样上抛到 UI；归档项目 SHALL 只读（新增研究线被拒）；删除 SHALL 仅对已归档放行。

#### Scenario: archive-then-delete over RPC
- **WHEN** delete runs on an active project, then archive, then a fork registration, then delete
- **THEN** responses are: rejection mentioning archive → ok → rejection mentioning archived → ok with the project gone from /api/tree
