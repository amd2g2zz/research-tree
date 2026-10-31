# tui-renderer

## Why

Issue #580 (user add, T1; docs 03 page logic): terminal users need the same trust face without a browser. The TUI is a **rendering surface, not a second behavior implementation** — same-source projection discipline as the web canvas (#559).

## What changes

- `tui/renderer.ts`: renderTuiFrame — a deterministic text frame over the ledger/event stream with sections SIDEBAR (task tree with 未冻结·不可跟踪 labels), PHASE (state machine phase with text status), CLAIMS (posterior/tier/weight rows), CONSOLE (transition tail), FROZEN banner (vN·hash·verdict + 继续研究=版本+1). Red lines: status never color-only, committed versions never imply modifiability. Interactive TUI toolkit is host-side.

## impact_scope

- `rt-core/src/tui/renderer.ts` (new)
- tests: `rt-core/test/tui_renderer.test.ts`
