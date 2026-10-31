## ADDED Requirements

### Requirement: no item starts before its trigger fires

每个学习层条目 SHALL 由其自身触发器逐项门控；触发器未点亮 SHALL 拒绝启动；冷遥测 SHALL 全员 dormant。

#### Scenario: cold telemetry leaves everything dormant
- **WHEN** evaluate runs on cold telemetry
- **THEN** fired is empty and start() on any item throws an UmbrellaError

#### Scenario: per-item gating
- **WHEN** only one item's threshold is met (e.g. experiments_count reaches 50)
- **THEN** exactly that item fires and the others stay dormant

### Requirement: loopx retirement is executable (清退)

loopx 适配器 SHALL 在 G1-G5 增益全部达标时点亮；不达标 SHALL 走可执行清退（审计事件落库），清退后 SHALL 永不重启。

#### Scenario: gains met fires, shortfall retires
- **WHEN** all G1-G5 gains meet the threshold the item fires; when any gain falls short and retirement executes
- **THEN** a retire audit event lands and a later start attempt throws mentioning retired

### Requirement: learning outputs stay prior-only (auditable by design)

学习层输出 SHALL 只为先验校准记录（kind=prior-calibration）且 SHALL 落审计事件；policy 形输出 SHALL 被拒绝（范围公理：只校准先验，永不学策略）。

#### Scenario: policy-shaped output rejected
- **WHEN** recordOutput is called with kind=policy
- **THEN** an UmbrellaError mentioning prior-only is thrown

#### Scenario: valid calibration audited
- **WHEN** a prior-calibration record lands
- **THEN** exactly one output audit event is appended

### Requirement: chained trigger for the L1 upgrade

l1-upgrade SHALL 仅在先验校准落地后解锁（链式触发）。

#### Scenario: L1 unlocks after calibration lands
- **WHEN** prior_calibration_landed flips true on a plateau
- **THEN** both p-refuted-calibration and l1-upgrade fire
