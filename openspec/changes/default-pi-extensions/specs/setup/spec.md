## ADDED Requirements

### Requirement: default pi extensions are provisioned idempotently on explicit action

5 个默认扩展 SHALL 可经设置页显式动作幂等供应：settings 已引用的跳过，缺失的安装并把路径追加进 pi settings packages（npm -g 不可写时回退 ~/.pi/agent/npm 本地前缀）；安装 SHALL NEVER 静默发生（#588），结果 SHALL 按名落审计。

#### Scenario: idempotent provisioning
- **WHEN** ensurePiExtensions runs twice with an injected installer
- **THEN** the second run reports the first batch as present and installs nothing

#### Scenario: failure reported without corrupting settings
- **WHEN** one extension's install fails
- **THEN** it is reported failed by name, the others land, and settings contains only successful paths

### Requirement: extension status is visible in settings

设置 SHALL 展示 5 个默认扩展的安装状态（/api/config/pi default_extensions）与显式安装按钮。

#### Scenario: status surfaces
- **WHEN** the settings modal opens
- **THEN** all five default extensions render with their installed state
