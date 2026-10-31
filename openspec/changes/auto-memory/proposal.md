# auto-memory

## Why

Issue #640 (L5 相邻, 用户裁定 2026-10-31): 研究要复利——任务里学到的教训、显性偏好、结局随会话消失。简单 auto memory：系统自动写入、按需有界召回、append-only、全链审计。

## What changes

- migration v7：`memories` 表（scope: user|project:<id>|task:<id>；kind 封闭四类 preference/lesson/source-baseline/outcome；content_hash 去重唯一索引；status active|superseded——append-only 永不物理删除）。
- `memory/store.ts`: AutoMemory —
  **remember**（溯源律：provenance 空拒绝；kind 封闭集=user-profile 红线钉死「永不按用户画像改变行为」；scope 格式校验；同 (scope,kind,content_hash) 幂等去重；写操作落 provider.action 审计事件）；
  **recall**（有界确定性召回：scope 精确 + user 层全局、active only、updated_at DESC + id tiebreak、limit + char_budget 双帽；KV-cache friendly）；
  **load**（lazy：溯源全文按需加载，#589 惰性披露模式）；
  **forget**（标记 superseded，理由进审计）；
  **harvest(taskId)**（机械自动写入：被驳主张 posterior≤0.1 → lesson；已提交裁决 → outcome；幂等）。
- prior-only 公理（L5）延续：记忆只影响先验，policy 形条目进不来（kind 封闭集即闸门）。

## impact_scope

- `rt-core/src/store/ledger.ts` (migration v7 append — MIGRATIONS registry, no external refs, text-confirmed)
- `rt-core/src/memory/store.ts` (new)
- tests: `rt-core/test/memory.test.ts`
