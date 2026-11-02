## ADDED Requirements

### Requirement: readiness probe over the pi single source

keyed-session 就绪 SHALL 由 pi 配置推导（auth.json 有 provider key ∧ models-store 有默认模型），SHALL 随 /api/config/pi 披露明细；掩码 SHALL 不变。

#### Scenario: probe flips with config
- **WHEN** the pi dir gains a provider key and a default model
- **THEN** keyed_session_ready flips true without any rt-side state

### Requirement: explicit kinds are respected; auto classification is disclosed

显式 kind SHALL 恒被尊重（classified_by=user）；缺省 kind SHALL 走 ClassificationPort——keyed 时 pi-session、否则 heuristic 回退；转写与回执 SHALL 记录 classified_by，SHALL NOT 假装自动。

#### Scenario: auto classifies with disclosure
- **WHEN** chat.ingest runs without a kind on a non-keyed server
- **THEN** the receipt carries classified_by=heuristic and routes via the mechanical router

#### Scenario: keyed server uses the pi session
- **WHEN** the pi runner (injected) returns strict JSON
- **THEN** classified_by=pi-session and the kind feeds the same mechanical router

### Requirement: classification fails closed

pi 分类返回不可信结果（无 JSON/malformed/越界 kind）SHALL 抛错——SHALL NOT 静默改道或猜测 kind。

#### Scenario: unusable answer rejected
- **WHEN** the injected pi runner returns non-JSON or an out-of-set kind
- **THEN** classification throws naming the failure
