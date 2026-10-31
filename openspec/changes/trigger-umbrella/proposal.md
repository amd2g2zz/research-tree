# trigger-umbrella

## Why

Issue #577 (T4, docs 01 L5): 学习层 trigger-driven——每项只在触发器点亮后建造，永不按日历。范围公理机械化执行：**只校准先验，永不端到端学策略**（可审计是产品需求）；loopx 适配器无期限延伸——不达标即清退（可执行）。

## What changes

- `learning/umbrella.ts`: LearningUmbrella + DEFAULT_ITEMS（7 项各带机械触发谓词，评估输入为累计遥测 TriggerData）——
  evaluate（逐项门控：fired/dormant）、start（**dormant 拒绝启动**——无项在触发器点亮前开工）、retireLoopx（可执行清退+审计事件，清退后永不重启）、recordOutput（**prior-only 红线**：kind ∉ prior-calibration 的输出（policy 形）拒绝；输出落审计事件）、l1-upgrade 链式触发（先验校准落地后解锁）。

## impact_scope

- `rt-core/src/learning/umbrella.ts` (new)
- tests: `rt-core/test/umbrella.test.ts`
