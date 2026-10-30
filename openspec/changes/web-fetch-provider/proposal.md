# web-fetch-provider

## Why

Issue #590 (user ruling 2026-10-30): third bundled provider — direct network requests, downloads, content extraction with deterministic summaries (plain text / code only), pdf/pptx/docx/xlsx → markdown. Tooling survey: **MarkItDown** (Microsoft, MIT, local CLI) covers the office/pdf conversions — reused, not reimplemented; HTML extraction reuses @mozilla/readability + turndown. Free/local stack, zero paid APIs.

## What changes

- `providers/web_fetch.ts`: fetch-only port adapter (kinds: web-page / pdf / office-doc):
  - HTML → Readability → turndown → markdown (title restored on top);
  - text/plain + code → raw text preserved + **deterministic summary** (title/outline/code-block inventory with naive language detection/line/byte counts — provider layer has zero LLM calls);
  - pdf/office → download (size cap + timeout) → markitdown CLI (positional file arg, real CLI shape) → markdown; extension+content-type sniffing;
  - HTTP errors / oversize / CLI failure → structured failures, never silent empty evidence;
  - injectable fetchFn + markitdown runner for deterministic tests.
- Routing split with #587: static resources here, JS-rendered pages there (EVSI/cost decides, decision in the audit event).

## impact_scope

- `rt-core/src/providers/web_fetch.ts` (new), `rt-core/src/providers/types.ts` (ProviderDocument.summary?: unknown — additive)
- deps: @mozilla/readability, turndown, jsdom (+types) — all free/open
- tests: `rt-core/test/web_fetch.test.ts`
