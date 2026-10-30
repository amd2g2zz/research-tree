# design — provider-port

## Patterns

- **Ports & adapters**: `DataSourceProvider` is the port; anysearch/agent-browser/web_fetch are adapters (the latter two land as #587/#590).
- **Decorator**: `auditedProvider` wraps any provider for the audit trail — the audit concern is orthogonal to retrieval, and the engine consumes only audited providers.
- **Structural dependency**: the decorator takes `AuditLog = { appendGraphEvent }` — EngineCore and the raw ledger both satisfy it; no coupling to the concrete store.

## Event vocabulary

`provider.action` (flat payload): id/provider/action(search|fetch)/target/outcome(ok|error)/result_count?/bytes?. The projection ignores it (log-only audit). Optional fields canonicalize absent → null; canonicalJson maps undefined → null defensively.

## rejected_designs

- Provider-specific ledger tables (audit lives in the event stream — the search envelope projects from events).
- Passing credentials through search/fetch calls (injected at construction; never serialized).
- Blocking CLI requirement in tests (injected runner; the real CLI is provisioned by #588).
- Builder-pattern registry (plain register/get/list/default suffices at T0 scale).
