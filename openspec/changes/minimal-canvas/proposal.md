# minimal-canvas

## Why

Issue #559 (T1 row 5, docs 03 §研究图谱 + 关键交互件): the canvas is the trust face of unattended research (看不见的研究不可信). T1 ships the **projection data layer** the react-flow canvas renders — canvas = pure projection of the ledger/event stream, writes only through the five gates.

## What changes

- `canvas/projection.ts`: CanvasProjection —
  - **same-source render**: the three-layer view (question → task → claims) derived purely from the ledger event stream (deterministic — same events, same canvas);
  - **five write gates** as the ONLY mutation surface: pause-resume / kill-stage / park (revival conditions mandatory) / verdict-confirm (closed vocabulary) / append-info — any other mutation is structurally impossible (no method exists);
  - provider identities surfaced from provider.action events (the audit trail is the canvas's provider layer).
- Status never color-only (text/icon always — red line carried from #559's design).

## impact_scope

- `rt-core/src/canvas/projection.ts` (new)
- tests: `rt-core/test/canvas.test.ts`
