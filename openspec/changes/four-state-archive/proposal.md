# four-state-archive

## Why

Issue #573 (T3 row 3, charter §3, docs 01 A6): 结局四态全部是成功，附着在版本上——GO→底稿交接；NO-GO→墓地（为何放弃+复活条件，可浏览）；PARK→冻结简报+强制复活条件（无复活条件的 PARK 是缺陷，红线钉死）；REFRAMED→新任务继承账本（fork 语义+delta 报告）。

## What changes

- migration v6：`archive_entries`（task_id, v 主键；verdict + 处置 JSON）。
- `versions/archive.ts`: FourStateArchive — archive（按裁决分发处置校验：NO-GO/PARK 复活条件强制、PARK 需冻结简报、REFRAMED 需继承任务+delta 报告并经 machine.forkTask 继承账本）、graveyard()（墓地可浏览）、revive()（**复活 = 从墓地版本 fork**，分叉即继承，血缘边落库，墓地条目记录 revived_to）、list/entry（四态可浏览）。

## impact_scope

- `rt-core/src/store/ledger.ts` (migration v6 append — MIGRATIONS registry, no external refs, text-confirmed)
- `rt-core/src/versions/archive.ts` (new)
- tests: `rt-core/test/versions_archive.test.ts`
