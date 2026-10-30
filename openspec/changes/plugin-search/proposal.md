# plugin-search

## Why

Issue #589 (user ruling 2026-10-30: "你不能一口气把所有插件全部注入到 context 里面吧，又慢又费 token"): provider full-usage guides never auto-enter context. The registry holds lightweight manifests; full usage loads only for selected providers. Precedent: the agent-browser discovery-stub (pointer stub + on-demand `skills get`); behavior strategy stays prompt-side per the #501 two-layer contract.

## What changes

- `ProviderRegistry` gains the lazy-disclosure surface:
  - `searchProviders({ capability | kind | keyword })` — retrieval over manifests (name/capabilities/kinds/description); usage bodies never ride the search.
  - `select(name)` / `selected()` — explicit selection gates usage loading.
  - `loadUsage(name, loader)` — cached by name, **refused for unselected providers** (the discipline is mechanical).
  - `loadedUsageCount()` — the measurable context-cost invariant: loaded ≤ selected.
- `docs/providers/*.md` usage stubs for the two bundled adapters (full guides grow there).

## impact_scope

- `rt-core/src/providers/registry.ts` (select/searchProviders/loadUsage/loadedUsageCount)
- tests: `rt-core/test/plugin_search.test.ts`, usage stubs `rt-core/docs/providers/*.md`
