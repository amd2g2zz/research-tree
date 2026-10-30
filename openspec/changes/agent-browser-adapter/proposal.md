# agent-browser-adapter

## Why

Issue #587 (user ruling 2026-10-30): the second bundled DataSourceProvider adapter — rendered-web fetch. anysearch covers general web search; agent-browser covers pages that only materialize after JS execution or need interaction/login state.

## What changes

- `providers/agent_browser.ts`: adapter over the agent-browser CLI (Rust + CDP; version pinned at provisioning, 0.31.1 baseline) — `read <url>` for agent-readable text, `open` + `snapshot` fallback for interaction-gated pages, headless in CI, structured failures (empty extraction / CLI error never yield silent empty evidence), search unsupported by contract.
- Injectable command runner (same pattern as the anysearch adapter).

## impact_scope

- `rt-core/src/providers/agent_browser.ts` (new)
- tests: `rt-core/test/agent_browser.test.ts`
