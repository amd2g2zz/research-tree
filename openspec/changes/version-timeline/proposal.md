# version-timeline

## Why

Issue #574 (T3 row 4, docs 03 P5 + 快照视图, docs 01 A7): 版本页时间线（vN/hash/裁决/摘要倒序 + 草稿行"未冻结·不可跟踪" + ⑂ 分叉标记）、主分支默认投影（切换恒为显式寻址）、继续研究/从此分叉、只读快照视图、H7 遥测。

## What changes

- `versions/timeline.ts`: VersionTimeline — timeline()（倒序+fork 标记+草稿行）、isMainBranch（无 fork parent）、defaultProjection（主支最新，分支尖端永不劫持）、continueResearch（version+1 写时复制 draft；**活动草稿优先恢复，永不覆盖未冻结工作**）、fork（分叉即继承→chat）、snapshotView（冻结横幅+报告投影；不可变是机械保证：append-only + 重复内容冻结拒绝）、H7 遥测（provider.action report 事件）。
- **schema**: provider.action 的 action 枚举追加 "report"（遥测载体，additive）。
- **修复（freeze 语义）**：freeze 消费草稿行（草稿不可跟踪——冻结后不留陈旧未冻结行）。影响分析：GitNexus impact(freeze) LOW，唯一调用方 machine.freezeTask；state_machine 测试按 A7 规则 3 改为先 openDraftFromVersion。

## impact_scope

- `rt-core/src/versions/timeline.ts` (new)
- `rt-core/src/versions/store.ts` (freeze consumes draft)
- `rt-core/src/events/schema.ts` (action enum + "report")
- tests: `rt-core/test/version_timeline.test.ts`, `rt-core/test/state_machine.test.ts` (v+1 flow per A7 rule 3)
