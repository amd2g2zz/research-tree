/** Data-source provider port (issue #584, docs/product/02 §数据源插件接口).

Retrieval capability belongs to providers; audit and verdict semantics belong
to the engine. Every search/fetch action is audited as a `provider.action`
event (the auditedProvider decorator) — swapping providers never changes audit
semantics. Credentials are injected at construction and never serialized into
events or the ledger.
*/

export interface ProviderCapabilities {
  search: boolean;
  fetch: boolean;
}

/** Lightweight manifest — the registry unit; full usage loads on demand (#589). */
export interface ProviderManifest {
  name: string;
  capabilities: ProviderCapabilities;
  kinds: string[];
  description: string;
  /** pointer to the full usage guide — never auto-loaded */
  usage: string;
}

export interface SearchQuery {
  query: string;
}

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

export interface ResourceRef {
  url: string;
}

export interface ProviderDocument {
  url: string;
  contentType: string;
  text: string;
  bytes: number;
  /** deterministic extraction summary (plain text / code only; #590) */
  summary?: unknown;
}

export interface DataSourceProvider {
  readonly manifest: ProviderManifest;
  search(query: SearchQuery): Promise<SearchResult[]>;
  fetch(ref: ResourceRef): Promise<ProviderDocument>;
}
