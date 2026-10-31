## ADDED Requirements

### Requirement: closed direction sources with a hard 8-arm cap

方向来源 SHALL 封闭为四种结构化生成来源，且 SHALL 硬上限 8 臂——第 9 个方向 parked（pinned），不顶替任何臂。

#### Scenario: the 9th direction parks
- **WHEN** 9 directions are registered
- **THEN** 8 become arms and the 9th persists with a parked history marker and zero allocation

#### Scenario: non-closed source rejected
- **WHEN** a direction declares a source outside the closed set
- **THEN** registration throws

### Requirement: four-signal arm value posterior

每臂价值后验 SHALL 由四信号（kill-存活率/证据产率/决策杠杆/意外度）池化为 Beta 后验，均值落盘，四信号 SHALL 进入 history 可追溯。

#### Scenario: signals order arms
- **WHEN** one arm receives strong signals and another weak ones
- **THEN** the strong arm's persisted value_posterior is higher and both histories carry the raw signals

### Requirement: seeded Thompson allocation

分配 SHALL 从各臂后验做种子化采样（同种子同结果），整轮预算 SHALL 给采样最高者。

#### Scenario: same seed reproduces allocation
- **WHEN** allocateRound runs twice with the same seed
- **THEN** winner and per-arm samples are identical and the winner receives the full round budget

### Requirement: deepen/widen triggers with a structural 30% widen cap

触发器 SHALL 机械判定：make-or-break 悬在 ~0.5 → deepen；全员 EVSI 跌破阈 → widen。widen 花费占累计预算比例 SHALL 结构性封顶 ≤30%，超出部分被削减。

#### Scenario: hanging make-or-break deepens
- **WHEN** the make-or-break posterior is 0.52
- **THEN** the round decision is deepen with a make-or-break reason

#### Scenario: all-arm EVSI below floor widens, capped
- **WHEN** every arm EVSI is below the floor and widen mode runs for 10 rounds
- **THEN** each round's decision is widen, and the cumulative widen share never exceeds 30% (equal to the cap at the end)

### Requirement: portfolio panel at round boundaries

组合面板 SHALL 在轮边界渲染 方向 × 价值后验 × 分配。

#### Scenario: panel renders arms with posteriors and allocation
- **WHEN** the panel is rendered after a round
- **THEN** it lists every arm with its source, value_posterior, allocation, and parked state
