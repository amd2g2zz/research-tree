/** Audit decorator for data-source providers (issue #584).

Wraps any DataSourceProvider and emits one `provider.action` event per
search/fetch — provider identity, target, outcome, and cheap metrics (result
count / byte count). Failures are recorded with outcome "error" and re-thrown
as a provider-envelope error: internal error details never leak into the event
stream, and provider credentials never do either (the decorator only touches
the manifest and the call arguments/results).
*/

import type { EventPayload } from "../store/ports.js";
import type { DataSourceProvider, ProviderDocument, ResourceRef, SearchQuery, SearchResult } from "./types.js";

export class ProviderActionError extends Error {}

let actionSeq = 0;

function nextActionId(): string {
  actionSeq += 1;
  return `provider-action-${actionSeq}`;
}

/** Structural dependency: the decorator only appends events. */
export type AuditLog = { appendGraphEvent(eventType: string, payload: EventPayload, options?: { runId?: string | null }): unknown };

export function auditedProvider(log: AuditLog, inner: DataSourceProvider): DataSourceProvider {
  const manifest = inner.manifest;
  const audit = async (
    action: "search" | "fetch",
    target: string,
    outcome: "ok" | "error",
    metrics: { result_count?: number; bytes?: number } = {},
  ): Promise<void> => {
    // best-effort telemetry: the ledger write inside appendGraphEvent is
    // synchronous (the event lands), and a projection failure after it is
    // repairable via resync — the provider action itself must not break.
    try {
      await log.appendGraphEvent("provider.action", {
        id: nextActionId(),
        provider: manifest.name,
        action,
        target,
        outcome,
        ...metrics,
      });
    } catch {
      // audit append failure never fails the provider action
    }
  };

  return {
    manifest,

    async search(query: SearchQuery): Promise<SearchResult[]> {
      try {
        const results = await inner.search(query);
        await audit("search", query.query, "ok", { result_count: results.length });
        return results;
      } catch (error: unknown) {
        await audit("search", query.query, "error");
        throw new ProviderActionError(`provider search failed: ${manifest.name}`);
      }
    },

    async fetch(ref: ResourceRef): Promise<ProviderDocument> {
      try {
        const document = await inner.fetch(ref);
        await audit("fetch", ref.url, "ok", { bytes: document.bytes });
        return document;
      } catch (error: unknown) {
        await audit("fetch", ref.url, "error");
        throw new ProviderActionError(`provider fetch failed: ${manifest.name}`);
      }
    },
  };
}
