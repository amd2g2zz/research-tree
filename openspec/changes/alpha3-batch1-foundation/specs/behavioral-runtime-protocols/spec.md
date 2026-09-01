## ADDED Requirements

### Requirement: 行为层必须通过具名 runtime API 处理四类治理交互

被打断、结论被质疑、交付验收、对齐期意图声明这四类交互场景，行为层文档（SKILL.template.md、research-quality-playbook.md、三 host adapter）必须包含具名协议段，指向真实存在的 `src/research_tree` runtime API。禁止以散文应付替代协议调用。

#### Scenario: 被打断必须走 correction 协议二选一
- **WHEN** 用户在 autonomous_research 阶段发出新 ask / 修正 / follow-up（即"被打断"）
- **THEN** 行为层按 `record_correction`（或 `apply_correction`）协议段处理，`kind` 必须在 reopen 与 supplement 中显式二选一，且选择被记录为 correction 事件；不得以自由文本回复绕过

#### Scenario: 结论被质疑必须走矛盾协议
- **WHEN** 用户或新证据与已交付结论冲突
- **THEN** 行为层驱动 `apply_contradiction`，触发 stale 交付标记与重入提议；不得静默改写结论或仅道歉

#### Scenario: 交付后必须收集五决议验收
- **WHEN** 交付进入 awaiting_acceptance
- **THEN** 行为层按 acceptance 协议段收集 accepted/rejected/needs_deeper_research/needs_intent_correction/partially_accepted 之一并记录

#### Scenario: 对齐期意图声明按 claim 抽取
- **WHEN** 对齐期用户做出意图/可行性声明
- **THEN** 行为层按 claim 抽取协议段将其作为可寻址声明处理（衔接 #316 的 claim 模型），不得作为无名自由文本合并

#### Scenario: 用户可见状态消息必须先查 canonical 状态
- **WHEN** 行为层准备生成任何"当前阶段/在等谁/下一步"类用户可见状态消息
- **THEN** 先读取 `research-tree status`（canonical 投影）再组织消息；不得凭会话记忆编造阶段

### Requirement: 行为层-运行时契约测试锁定文档引用的真伪

仓库必须包含契约测试，使行为层文档与 runtime API 之间的引用关系可被机器验证。

#### Scenario: 文档引用不存在的 API 时测试失败
- **WHEN** 任一行为层文档按名引用的 runtime API 在 `src/research_tree/` 中不存在、不可导入、或文档所述关键参数与实际签名不符
- **THEN** `tests/test_behavioral_layer_contract.py` 失败并指出具体文档位置与 API 名

#### Scenario: 名单制扫描避免历史名词误报
- **WHEN** 文档包含不在协议 API 白名单内的历史名词或示例
- **THEN** 契约测试不扫描该名词（仅校验白名单集合），测试不误报

### Requirement: 行为层文档改动必须保持三份 host 包一致

#### Scenario: skill-src 改动后 packages 仍一致
- **WHEN** SKILL.template.md / playbook / 任一 adapter 被修改并提交
- **THEN** `uv run --frozen python scripts/build_skill_packages.py --check` 通过（packages/ 三份为重生成后的当前态）
