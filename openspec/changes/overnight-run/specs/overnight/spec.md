## ADDED Requirements

### Requirement: the 12h hard cap forces convergence (the run never hangs)

全局预算硬帽 SHALL 强制收敛：到达帽后 SHALL 跑一轮 final 轮——信息充分则强制收敛，否则 PARK；运行 SHALL 永不挂起。

#### Scenario: research converges naturally within the cap
- **WHEN** a round reports done before the cap
- **THEN** the run converges with forced=false

#### Scenario: cap forces convergence
- **WHEN** the cap is reached without natural convergence and the final round reports info_sufficient
- **THEN** the run converges with forced=true and terminates

### Requirement: PARK fallback with revival conditions

信息不足时 SHALL 回落 PARK，且 PARK SHALL 带非空复活条件（产品红线）——空复活条件 SHALL 被拒绝。

#### Scenario: info insufficient at the cap parks with revival conditions
- **WHEN** the final round reports info_sufficient=false with revival conditions
- **THEN** the outcome is parked and the conditions are surfaced

#### Scenario: empty revival conditions rejected
- **WHEN** the final round reports info_sufficient=false with an empty revival list
- **THEN** an OvernightError mentioning revival conditions is thrown

### Requirement: round limit fails closed

不收敛且不推进时钟的 round executor SHALL 在轮数上限处 fail-closed 为 PARK（带复活条件），SHALL NOT 无限空转。

#### Scenario: round limit exceeded parks
- **WHEN** the round executor never converges and max_rounds is reached
- **THEN** the outcome is parked with a round-limit revival condition

### Requirement: mid-run crash resumes from the event log without ledger corruption

崩溃恢复 SHALL 先校验哈希链（防篡改）再从 task.transition 事件 rehydrate 状态机，续跑 SHALL 延续同一账本（resumes, not restarts），恢复后链 SHALL 仍完整。

#### Scenario: recovery protocol verifies and rehydrates
- **WHEN** recoverFromCrash runs after a mid-run crash
- **THEN** the chain verifies, the rehydrated phase matches the pre-crash phase, and the event count is unchanged

#### Scenario: resumed run converges without corruption
- **WHEN** a recovered run continues and converges
- **THEN** the result carries recovered=true and verifyGraphChain passes
