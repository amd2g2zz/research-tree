## ADDED Requirements

### Requirement: typed provenance-bound writes with closed kinds

记忆 SHALL 携带非空溯源（溯源律）且 kind SHALL 属封闭四类（preference/lesson/source-baseline/outcome）——user-profile 类 SHALL 被拒绝（产品红线：永不按用户画像改变行为）；同 (scope, kind, content) SHALL 幂等去重；每次写 SHALL 落审计事件。

#### Scenario: three rejections pinned
- **WHEN** remembering with empty provenance, a non-closed kind, or a malformed scope
- **THEN** each attempt throws a MemoryError naming the violated rule

#### Scenario: idempotent dedupe
- **WHEN** the same content is remembered twice under different ids
- **THEN** the second call returns the first entry and recall counts one

### Requirement: bounded deterministic recall with lazy detail

召回 SHALL 确定（同 query 同序同量）、有界（limit + char_budget 双帽）、仅含 active 条目（scope 精确 + user 层全局，project 层零串扰）；溯源全文 SHALL 仅经 load(id) 按需加载。

#### Scenario: bounded and deterministic
- **WHEN** recall runs twice with the same query
- **THEN** both results are identical, within limit and char budget

#### Scenario: user layer global, project layers isolated
- **WHEN** recalling in project:pA and project:pB
- **THEN** user-scope entries appear in both; pA entries never appear in pB

### Requirement: append-only forgetting and mechanical harvest

forget SHALL 标记 superseded（行 SHALL 保留，物理删除不存在）且理由 SHALL 进审计；harvest(taskId) SHALL 机械写入——被驳主张（posterior ≤0.1）→ lesson、已提交裁决 → outcome——且 SHALL 幂等（重复 harvest 零重复）。

#### Scenario: forget then recall
- **WHEN** a memory is forgotten
- **THEN** recall loses it, the row remains with status superseded, and one forget audit event lands

#### Scenario: harvest idempotent
- **WHEN** harvest runs twice on the same task
- **THEN** the second run writes nothing new
