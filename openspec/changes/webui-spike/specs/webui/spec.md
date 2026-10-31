## ADDED Requirements

### Requirement: the browser drives one full research round over WS/REST

浏览器 SHALL 能经 WS/REST 驱动一整轮研究（建项目→注册主线→chat 路由→分解确认→签署→研究→冻结提交），全部 LLM 工作留在 pi host 边界，状态落在真实账本，首页 vitals 实时更新。

#### Scenario: full round over the wire
- **WHEN** the WS/REST sequence (create → registerTask → 3× chat.ingest → research.launch with pre-signed verdict) runs
- **THEN** the launch outcome is success, engine events stream over the socket, and vitals show v0 with verdict and 64-char hash

#### Scenario: chat four-way routing over RPC
- **WHEN** preference / guess / branch utterances are ingested
- **THEN** receipts route to slot / hypothesis-ledger / parking-lot respectively

### Requirement: pi config is the single source, read-only, key values masked

pi 配置 SHALL 只从 pi 自身目录读取（models + 默认模型 + auth provider 名）；key 值 SHALL 永不出现在任何对外输出；配置探针缺失/损坏 SHALL 降级为 null 而非崩溃。

#### Scenario: masking red line
- **WHEN** auth.json contains a key value and the summary is serialized
- **THEN** the key value is absent from the output while provider names are present

### Requirement: engine errors surface verbatim over the wire

引擎侧类型化错误 SHALL 原样上抛到 RPC/REST 调用方（不吞不包装成 500）。

#### Scenario: typed errors over the wire
- **WHEN** an invalid utterance kind / unknown project is sent
- **THEN** the RPC rejects with the engine's message and REST returns 404 for unknown vitals
