import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ProviderRegistry } from "../src/providers/registry.js";
import { AnysearchProvider } from "../src/providers/anysearch.js";
import { AgentBrowserProvider } from "../src/providers/agent_browser.js";

const USAGE_FILES: Record<string, string> = {
  "docs/providers/anysearch.md": "# anysearch usage\n\nFull guide: flags, output shapes, quota notes. ".repeat(40),
  "docs/providers/agent-browser.md": "# agent-browser usage\n\nFull guide: read/open/snapshot, profiles. ".repeat(40),
};

let workspace: string;
let registry: ProviderRegistry;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-pluginsearch-"));
  registry = new ProviderRegistry();
  registry.register(new AnysearchProvider({ runner: async () => ({ stdout: "[]", exitCode: 0 }) }));
  registry.register(new AgentBrowserProvider({ runner: async () => ({ stdout: "", exitCode: 0 }) }));
});

const loader = (pointer: string): string => {
  const text = USAGE_FILES[pointer];
  if (text === undefined) {
    throw new Error(`usage file missing: ${pointer}`);
  }
  return text;
};

describe("provider search over manifests", () => {
  it("finds providers by kind", () => {
    const hits = registry.searchProviders({ kind: "web-rendered" });
    expect(hits.map((m) => m.name)).toEqual(["agent-browser"]);
  });

  it("finds providers by capability", () => {
    const hits = registry.searchProviders({ capability: "search" });
    expect(hits.map((m) => m.name)).toEqual(["anysearch"]);
  });

  it("free-text matches descriptions", () => {
    const hits = registry.searchProviders({ keyword: "browser" });
    expect(hits.map((m) => m.name)).toEqual(["agent-browser"]);
  });

  it("returns manifest lines only — usage bodies never ride the search", () => {
    const hits = registry.searchProviders({ keyword: "search" });
    const serialized = JSON.stringify(hits);
    expect(serialized).not.toContain("Full guide");
    expect(serialized).not.toContain("quota notes");
  });
});

describe("lazy usage disclosure", () => {
  it("loads usage only for selected providers", () => {
    registry.select("anysearch");
    const usage = registry.loadUsage("anysearch", loader);
    expect(usage).toContain("anysearch usage");
    expect(() => registry.loadUsage("agent-browser", loader)).toThrow(/not selected/);
  });

  it("caches loaded usage — one entry per provider regardless of load count", () => {
    registry.select("anysearch");
    registry.select("agent-browser");
    const first = registry.loadUsage("anysearch", loader);
    const second = registry.loadUsage("anysearch", loader);
    expect(second).toBe(first);
    expect(registry.loadedUsageCount()).toBe(1);
    registry.loadUsage("agent-browser", loader);
    expect(registry.loadedUsageCount()).toBe(2);
  });

  it("keeps the invariant: loaded usage never exceeds selected providers", () => {
    registry.select("anysearch");
    registry.loadUsage("anysearch", loader);
    // agent-browser usage exists on disk but is NOT selected — never loaded
    registry.select("agent-browser");
    registry.loadUsage("agent-browser", loader);
    expect(registry.loadedUsageCount()).toBeLessThanOrEqual(registry.selected().length);
    expect(registry.selected()).toEqual(["agent-browser", "anysearch"]); // sorted
  });
});
