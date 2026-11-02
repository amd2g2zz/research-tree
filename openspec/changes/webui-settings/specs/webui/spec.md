## ADDED Requirements

### Requirement: config writes modify pi's own files only (single source)

设置写 SHALL 直接修改 pi 自身配置（auth.json / models-store.json，原子写+写后读校验），rt 侧 SHALL NOT 存在任何副本；非法输入 SHALL 被拒绝且不触文件。

#### Scenario: key lands in pi's file, verified
- **WHEN** config.setProviderKey runs
- **THEN** pi's auth.json contains the key (verified by re-read) and no rt-side copy exists

### Requirement: key values never surface; audit records names only

key 值 SHALL 永不出现在任何对外输出（read 掩码、RPC 响应、审计事件）；审计 SHALL 只记 provider 名/模型名。

#### Scenario: masking holds after a write
- **WHEN** a key is written and the config summary and audit events are serialized
- **THEN** neither contains the key value while provider names are present

### Requirement: model switch takes effect for new pi sessions

默认模型写入 SHALL 经写后读校验回读一致；语义 SHALL 如实披露（新开的 pi 会话生效，进行中会话不打断）。

#### Scenario: default model verified
- **WHEN** config.setDefaultModel runs
- **THEN** the summary's default_model equals the written model
