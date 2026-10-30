import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { GraphStore } from "../src/graph/projection.js";
import { LedgerStore } from "../src/store/ledger.js";
import { EngineCore } from "../src/store/engine.js";
import { ProviderRegistry } from "../src/providers/registry.js";
import { AnysearchProvider } from "../src/providers/anysearch.js";
import { auditedProvider } from "../src/providers/audited.js";
import type { DataSourceProvider } from "../src/providers/types.js";

const MANIFEST = {
  name: "anysearch",
  capabilities: { search: true, fetch: false },
  kinds: ["web-search"],
  description: "general web search (default provider)",
  usage: "docs/providers/anysearch.md",
};

let workspace: string;
let ledger: LedgerStore;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-providers-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

class FakeProvider implements DataSourceProvider {
  readonly manifest = {
    name: "fake",
    capabilities: { search: true, fetch: true },
    kinds: ["web-search"],
    description: "fixture provider",
    usage: "docs/providers/fake.md",
  };

  async search() {
    return [{ title: "t", url: "https://example.com", snippet: "s" }];
  }

  async fetch() {
    return { url: "https://example.com", contentType: "text/plain", text: "hello", bytes: 5 };
  }
}

describe("provider registry", () => {
  it("registers, lists and resolves providers by name", () => {
    const registry = new ProviderRegistry();
    const provider = new FakeProvider();
    registry.register(provider);
    expect(registry.names()).toEqual(["fake"]);
    expect(registry.get("fake")).toBe(provider);
    expect(registry.get("missing")).toBeUndefined();
  });

  it("rejects duplicate names and keeps the default resolvable", () => {
    const registry = new ProviderRegistry();
    registry.register(new FakeProvider());
    expect(() => registry.register(new FakeProvider())).toThrow(/already registered/);
    const anysearch = new AnysearchProvider({ runner: async () => ({ stdout: "[]", exitCode: 0 }) });
    registry.register(anysearch);
    registry.setDefault("anysearch");
    expect(registry.default()).toBe(anysearch);
  });

  it("lists manifests only (name/capabilities/kinds/description/usage)", () => {
    const registry = new ProviderRegistry();
    registry.register(new AnysearchProvider({ runner: async () => ({ stdout: "[]", exitCode: 0 }) }));
    const manifests = registry.manifests();
    expect(manifests).toEqual([
      {
        name: "anysearch",
        capabilities: { search: true, fetch: false },
        kinds: ["web-search"],
        description: "general web search (default provider)",
        usage: "docs/providers/anysearch.md",
      },
    ]);
    expect(JSON.stringify(manifests)).not.toContain("apiKey");
  });
});

describe("anysearch adapter", () => {
  it("maps CLI json output to search results", async () => {
    const runnerOutput = JSON.stringify([
      { title: "Result A", url: "https://a.example.com", snippet: "first" },
      { title: "Result B", url: "https://b.example.com", snippet: "second" },
    ]);
    const provider = new AnysearchProvider({
      runner: async (command, args) => {
        expect(command).toBe("anysearch");
        expect(args).toContain("--json");
        return { stdout: runnerOutput, exitCode: 0 };
      },
    });
    const results = await provider.search({ query: "research-tree" });
    expect(results).toHaveLength(2);
    expect(results[0]).toEqual({ title: "Result A", url: "https://a.example.com", snippet: "first" });
  });

  it("raises a structured failure on a non-zero CLI exit", async () => {
    const provider = new AnysearchProvider({
      runner: async () => ({ stdout: "gateway down", exitCode: 1 }),
    });
    await expect(provider.search({ query: "q" })).rejects.toThrow(/anysearch search failed/);
  });

  it("does not support fetch", async () => {
    const provider = new AnysearchProvider({ runner: async () => ({ stdout: "[]", exitCode: 0 }) });
    await expect(provider.fetch({ url: "https://example.com" })).rejects.toThrow(/fetch/);
  });

  it("never includes credentials in emitted audit events", async () => {
    const engine = new EngineCore(ledger);
    const provider = auditedProvider(engine, new AnysearchProvider({
      config: { apiKey: "sk-secret-123" },
      runner: async () => ({ stdout: "[]", exitCode: 0 }),
    }));
    await provider.search({ query: "q" });
    const serialized = JSON.stringify(engine.graphEvents());
    expect(serialized).not.toContain("sk-secret-123");
  });
});

describe("audit decorator", () => {
  it("emits provider.action events for search and fetch", async () => {
    const engine = new EngineCore(ledger);
    const provider = auditedProvider(engine, new FakeProvider());
    await provider.search({ query: "hello" });
    await provider.fetch({ url: "https://example.com" });
    const actions = engine
      .graphEvents()
      .filter((event) => event.event_type === "provider.action")
      .map((event) => event.payload as Record<string, unknown>);
    expect(actions).toHaveLength(2);
    expect(actions[0]).toMatchObject({ provider: "fake", action: "search", target: "hello", outcome: "ok", result_count: 1 });
    expect(actions[1]).toMatchObject({ provider: "fake", action: "fetch", target: "https://example.com", outcome: "ok", bytes: 5 });
  });

  it("records failures with outcome error and no throw leak of internals", async () => {
    const engine = new EngineCore(ledger);
    const failing: DataSourceProvider = {
      manifest: { ...new FakeProvider().manifest },
      search: async () => {
        throw new Error("gateway down");
      },
      fetch: async () => {
        throw new Error("gateway down");
      },
    };
    const provider = auditedProvider(engine, failing);
    await expect(provider.search({ query: "q" })).rejects.toThrow(/provider search failed/);
    const actions = engine
      .graphEvents()
      .filter((event) => event.event_type === "provider.action")
      .map((event) => event.payload as Record<string, unknown>);
    expect(actions[0]).toMatchObject({ provider: "fake", action: "search", outcome: "error" });
    expect(JSON.stringify(actions)).not.toContain("gateway down");
  });

  it("keeps the projection unchanged by provider actions (audit events are log-only)", async () => {
    const store = new GraphStore(join(workspace, "graph.kuzu"));
    const engine = new EngineCore(ledger, store);
    const provider = auditedProvider(engine, new FakeProvider());
    await provider.search({ query: "hello" });
    const snapshot = await store.snapshotState();
    expect(snapshot.Claim).toEqual({});
    expect(snapshot.Stage).toEqual({});
  });
});
