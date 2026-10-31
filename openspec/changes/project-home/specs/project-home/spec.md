## ADDED Requirements

### Requirement: home vitals reflect live state

三体征 SHALL 反映实时状态：研究线数、主分支最新版本+裁决+hash、主线已用时间；fork 增线 SHALL 增加线数且 SHALL NOT 改变主分支最新版本。

#### Scenario: vitals empty then live
- **WHEN** a project is created and its main task commits v0
- **THEN** vitals go from {research_lines: 0, latest: null} to line count reflecting forks and latest v0 with verdict and 64-char hash

### Requirement: default projection is the main branch's latest version (A7 rule 5)

默认投影 SHALL 恒为主分支最新版本——fork 的更新提交 SHALL NOT 劫持首页。

#### Scenario: fork commits never hijack the home view
- **WHEN** the main line is at v1 and a fork commits a newer version
- **THEN** defaultProjection still returns main v1

### Requirement: card wall management with archive-only delete

卡片墙 SHALL 支持建/列/归档/删；删除 SHALL 仅对已归档项目放行，未归档删除 SHALL 被拒绝；归档项目 SHALL 只读（不得新增研究线）。

#### Scenario: delete blocked then allowed
- **WHEN** deleteProject runs on an active project, then after archiveProject
- **THEN** the first call throws mentioning archive, the second removes the project

#### Scenario: archived projects are read-only
- **WHEN** registerTask runs on an archived project
- **THEN** a ProjectHomeError is thrown

### Requirement: multi-project isolation

所有查询 SHALL 按 project_id 作用域化——并行项目的 vitals/归档/删除 SHALL 零串扰。

#### Scenario: zero cross-talk
- **WHEN** project A commits and is archived while project B idles
- **THEN** B's vitals stay empty and B's status stays active
