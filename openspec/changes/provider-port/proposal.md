# provider-port

## Why

Issue #584 (T0 row, docs/product/02 §数据源插件接口 v2.3): retrieval capability is pluggable — general search via **anysearch (default)**, enterprise data via Lark/db adapters later. Retrieval belongs to providers; audit and verdict semantics belong to the engine.

## What changes

- `providers/types.ts`: `DataSourceProvider` port (capabilities/search/fetch) + manifest/result types; the manifest (name/capabilities/kinds/description/usage pointer) is the registry unit.
- `providers/registry.ts`: named registry, config-driven default (bundled: anysearch), manifests-only listing (the #589 lazy-disclosure surface starts here).
- `providers/anysearch.ts`: first adapter — wraps the anysearch CLI (v1 vendored v2.1.0 semantics, revision pinned at provisioning); injectable command runner for deterministic tests; structured failure on non-zero exit; fetch unsupported by contract.
- `providers/audited.ts`: audit decorator — one `provider.action` event per search/fetch (provider identity, target, outcome, cheap metrics); failures recorded as outcome "error" with internals never leaked; credentials never enter events (pinned).
- Event vocabulary: `provider.action` added (flat payload,向后兼容追加); projection handler is a no-op — audit events live in the log, the graph stays unchanged.

## impact_scope

- `rt-core/src/providers/{types,registry,anysearch,audited}.ts` (new)
- `rt-core/src/events/{schema,canonical}.ts` (provider.action type + optional-field canonical null)
- `rt-core/src/graph/projection.ts` (no-op handler)
- tests: `rt-core/test/{providers,events}.test.ts`
