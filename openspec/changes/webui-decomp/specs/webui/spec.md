## ADDED Requirements

### Requirement: the card wall drafts before confirmation with mechanical gating

分解 SHALL 先以草稿态落盘（溯源律过滤无源要素并如实计数），充分性 checklist SHALL 机械计算（六类各 ≥1，拒绝点显式为无；难点≥1 未映射 kill 候选=缺口）；缺口 SHALL 阻止确认（预注册缺口，verbatim）。

#### Scenario: gaps block confirm
- **WHEN** an incomplete draft is confirmed
- **THEN** the engine rejects with a pre-registration gap naming the missing classes

#### Scenario: phantom elements dropped honestly
- **WHEN** an element without provenance is prepared
- **THEN** it is dropped (dropped=1) and the checklist names the emptied class as a gap

### Requirement: editing rights exist only before confirmation

确认前 SHALL 可逐卡删除（重起草）；确认后要素集 SHALL 冻结——再编辑 SHALL 被拒绝（重大转向重签，verbatim），确认 SHALL 挂载状态机使后续走查直通（attach 同一已确认集为幂等 no-op）。

#### Scenario: freeze after confirm
- **WHEN** removeElement runs on a confirmed decomposition
- **THEN** it is rejected mentioning major pivot, and a subsequent research.launch with the same id succeeds
