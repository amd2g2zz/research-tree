## ADDED Requirements

### Requirement: server-side structured pi calls run without the tool surface

server 端结构化调用（分类/回路/提取）SHALL 以 \`-nt\`（禁用工具面）运行——它们只需要文本 JSON，不需要工具执行；实测扩展加载下延迟 60s→18s。分类超时 SHALL 对齐 300s；信号杀死 SHALL 产出含重试指引的 typed 错误。

#### Scenario: -nt at call sites
- **WHEN** chat.turn / classification / extraction spawn pi
- **THEN** the args include -nt and the parse layers are unchanged
