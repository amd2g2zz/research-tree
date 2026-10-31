# timeline-scrubber

## Why

Issue #572 (T3 row 2, charter §6): 账本是 append-only 的——任意时刻 t 的画布是事件 ≤ t 的纯投影。拖动回放条到任意一拍，图谱与 console 同步（把 #559 重放条扩展为全场跑回放——"研究怎么走到今天"）。

## What changes

- `canvas/scrubber.ts`: TimelineScrubber over #546 事件流 + GraphStore.rebuild —
  beats()（全场拍列表+事件摘要）、projectionAt(t)（事件前缀 → 图快照 + console 行，越界钳制）、确定性（同拍重复 scrub 与新库 scrub 结果全等——#546 重放性质的属性测试）。

## impact_scope

- `rt-core/src/canvas/scrubber.ts` (new)
- tests: `rt-core/test/scrubber.test.ts`
