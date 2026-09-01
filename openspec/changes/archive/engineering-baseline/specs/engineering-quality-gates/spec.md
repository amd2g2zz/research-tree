## ADDED Requirements

### Requirement: lint 门覆盖复杂度与语言问题
`ruff check` 必须启用 C90/PLR/PLW/ARG/SIM/B/I 规则族；存量违例只能以显式豁免（per-file-ignores 或 noqa 带原因）存在，新代码零豁免。

#### Scenario: 扩展规则全量绿
- **WHEN** 运行 `uv run --frozen ruff check .`
- **THEN** exit 0（豁免显式、可列举）

### Requirement: 格式门全量绿且 CI 强制
`ruff format --check .` 在全仓绿；CI delivery-governance.yml 含同门。

#### Scenario: 格式检查通过
- **WHEN** 运行 `uv run --frozen ruff format --check .`
- **THEN** exit 0

### Requirement: 环境依赖测试必须可复跑或显式 skip
依赖 Docker daemon 的测试在 daemon 停机时必须显式 skip 并打印原因，不得环境性红。

#### Scenario: Docker daemon 停机
- **WHEN** docker CLI 存在但 daemon 不可达
- **THEN** hermes loader 测试 SKIPPED 且输出含原因

### Requirement: pydantic 注解边界显式
新模块 schema 定义走 pydantic（extra="forbid"）；存量模块不回填，回填排期由 ADR-007 记录。

#### Scenario: schemas 试点边界
- **WHEN** 检查 `src/research_tree/schemas.py`
- **THEN** pydantic 模型存在且拒绝额外字段
