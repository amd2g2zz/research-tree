# design — agent-browser-adapter

Same adapter pattern as anysearch (#584): port implementation + injectable
command runner + structured failures. Fetch pipeline: `read <url>` →
empty? `open <url>` + `snapshot` → document(contentType text/markdown, bytes =
utf8 length). Failure modes: non-zero exit (any step) and empty extraction —
both raise before a Document can exist.

## impact_scope

- new `rt-core/src/providers/agent_browser.ts`; tests
  `rt-core/test/agent_browser.test.ts` — no existing callers (registry
  registration lands with the consuming wave).

## rejected_designs

- Playwright/Puppeteer dependency (agent-browser is the CLI-standard, no extra
  runtime).
- Silent empty documents on bot walls (audit would record a lie).
- Login-state cookie jars in the engine (per-run browser profile config stays
  provider-level, injected).
