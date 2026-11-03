## ADDED Requirements

### Requirement: recon failure degrades instead of killing the turn

侦查 provider 失败 SHALL NOT 拖垮 chat.turn：回应 SHALL 照常落盘，转写 SHALL 落一条诚实的失败侦查行（含原因与"回应不受影响"），审计 SHALL 记 outcome=error，turn 结果 SHALL 带 recon_error。

#### Scenario: provider failure degrades
- **WHEN** the recon provider throws on a turn
- **THEN** the reply survives in the transcript, a failed-recon line lands, and the result carries recon_error

### Requirement: the vendored anysearch skill CLI is a real provider

server 默认 provider SHALL 在 skill CLI 存在时使用 SkillSearchProvider（spawn node CLI positional query，解析 markdown 结果块为 SearchResult[]）；缺失时 SHALL 回退 AnysearchProvider。

#### Scenario: markdown parses
- **WHEN** the CLI's markdown output is parsed
- **THEN** each result block yields title/URL/snippet
