## ADDED Requirements

### Requirement: real extraction from the chat transcript via the pi session

分解 SHALL 从对话转写经 pi 会话真实提取：quote SHALL 逐字回查转写消息（溯源律机械映射）；映射不上的要素 SHALL 被诚实丢弃并计数；keyed 未就绪 SHALL fail-closed（不提供模拟提取）；pi 二进制缺失 SHALL 报错指明 RT_PI_CMD。

#### Scenario: quotes map back; unkeyed refuses
- **WHEN** fromChat runs on a keyed server with an injected runner
- **THEN** dropped=0 and every element carries msg:seq provenance; on an unkeyed server the same call refuses mentioning the keyed session

### Requirement: mechanical start and human-signed freeze

research.start SHALL 要求已确认分解、以 claims_preview 机械生成阶段并注册 DAG、走查落在 research 相位；冻结 SHALL 经人工裁决门（四态 verdict），签署后 v0 落库、相位回 chat；非法 verdict SHALL 被拒绝。

#### Scenario: start then freeze
- **WHEN** research.start runs on a confirmed decomposition and research.freeze signs GO
- **THEN** phase=research with 1 stage registered, then v0 GO committed and phase back at chat

### Requirement: settings follow pi agent by default

设置 SHALL 读 pi 的 models.json providers（真实清单，key 掩码）；未设置覆盖时 SHALL 披露「跟随 pi agent 默认配置」；写 provider SHALL upsert 进 pi 自己的 models.json（schema 兼容）；归档项目 SHALL 收进侧栏「归档」文件夹。

#### Scenario: follows pi default and upserts provider
- **WHEN** no override is set and a provider is saved
- **THEN** follows_pi_default was true before, models.json gains the provider entry, and archived projects render under the 归档 folder
