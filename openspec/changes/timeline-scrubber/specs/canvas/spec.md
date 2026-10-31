## ADDED Requirements

### Requirement: the canvas at any t is a pure projection of events <= t

任意拍 t 的画布 SHALL 是事件 ≤ t 的纯投影：图快照与 console 行 SHALL 同源自同一事件前缀，越界 SHALL 钳制到有效区间。

#### Scenario: posterior update invisible at earlier beats
- **WHEN** beat 4 updates a claim's posterior and the scrubber projects t=2
- **THEN** the claim still shows the earlier posterior and the console has exactly 2 lines

#### Scenario: clamped ranges
- **WHEN** projecting t=0 or t beyond the last beat
- **THEN** the projection clamps to the empty prefix / full stream respectively

### Requirement: projection(t) is deterministic from the event stream

projection(t) SHALL 可从事件流复现：同拍重复 scrub 与全新存储 scrub SHALL 全等（#546 重放性质）。

#### Scenario: repeated and fresh scrubs identical
- **WHEN** the same beat is projected twice on one scrubber and once on a fresh scrubber over the same ledger
- **THEN** snapshot and console are identical in all three cases
