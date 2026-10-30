# anysearch — usage guide (default search provider)

General web search over the anysearch CLI. Provisioned by `rt setup` (#588): CLI on PATH + API key via injected env.

## Search

`search({ query })` → results `{ title, url, snippet }[]` (JSON array from the CLI).

- Query shape: natural-language research queries; the engine logs every search as a `provider.action` audit event.
- Quota/cost notes: provider quota profile feeds EVSI/cost routing (#557) — cheap first hop for web facts.
- Failure: non-zero CLI exit → structured provider failure (audit records outcome "error").

Not fetch-capable by contract: page materialization routes to agent-browser (#587) or web_fetch (#590) by EVSI/cost.
