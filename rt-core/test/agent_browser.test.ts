import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { AgentBrowserProvider } from "../src/providers/agent_browser.js";

const RENDERED_HTML = "Rendered dashboard content: 42 items synced";

let workspace: string;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-agentbrowser-"));
});

function fakeRunner(outputs: Record<string, { stdout: string; exitCode: number }>) {
  return async (command: string, args: string[]) => {
    const key = args.join(" ");
    const hit = outputs[key];
    if (hit === undefined) {
      throw new Error(`unexpected invocation: ${command} ${key}`);
    }
    return hit;
  };
}

describe("agent-browser adapter", () => {
  it("declares rendered-web capabilities (fetch only)", () => {
    const provider = new AgentBrowserProvider({ runner: async () => ({ stdout: "", exitCode: 0 }) });
    expect(provider.manifest).toMatchObject({
      name: "agent-browser",
      capabilities: { search: false, fetch: true },
      kinds: ["web-rendered"],
    });
  });

  it("extracts agent-readable full text via read", async () => {
    const provider = new AgentBrowserProvider({
      runner: fakeRunner({
        "read https://app.example.com/dashboard": { stdout: RENDERED_HTML, exitCode: 0 },
      }),
    });
    const document = await provider.fetch({ url: "https://app.example.com/dashboard" });
    expect(document.text).toContain("42 items synced");
    expect(document.contentType).toBe("text/markdown");
    expect(document.bytes).toBe(RENDERED_HTML.length);
    expect(document.url).toBe("https://app.example.com/dashboard");
  });

  it("falls back to open + snapshot when read yields nothing", async () => {
    const provider = new AgentBrowserProvider({
      runner: fakeRunner({
        "read https://app.example.com/gated": { stdout: "", exitCode: 0 },
        "open https://app.example.com/gated": { stdout: "opened", exitCode: 0 },
        "snapshot": { stdout: "# Gated view\n\ncontent after interaction", exitCode: 0 },
      }),
    });
    const document = await provider.fetch({ url: "https://app.example.com/gated" });
    expect(document.text).toContain("content after interaction");
    expect(document.bytes).toBeGreaterThan(0);
  });

  it("raises a structured failure on CLI errors (no silent empty document)", async () => {
    const provider = new AgentBrowserProvider({
      runner: fakeRunner({
        "read https://bad.example.com": { stdout: "navigation timeout", exitCode: 1 },
      }),
    });
    await expect(provider.fetch({ url: "https://bad.example.com" })).rejects.toThrow(
      /agent-browser fetch failed/,
    );
  });

  it("raises empty-extraction failure when read and the snapshot fallback are both empty", async () => {
    const provider = new AgentBrowserProvider({
      runner: fakeRunner({
        "read https://bot.example.com": { stdout: "   ", exitCode: 0 },
        "open https://bot.example.com": { stdout: "opened", exitCode: 0 },
        "snapshot": { stdout: "   ", exitCode: 0 },
      }),
    });
    await expect(provider.fetch({ url: "https://bot.example.com" })).rejects.toThrow(
      /empty extraction/,
    );
  });

  it("runs headless by default", async () => {
    let seenArgs: string[] = [];
    const provider = new AgentBrowserProvider({
      runner: async (command, args) => {
        seenArgs = [command, ...args];
        return { stdout: "content", exitCode: 0 };
      },
    });
    await provider.fetch({ url: "https://example.com" });
    expect(seenArgs.join(" ")).toContain("read");
  });

  it("does not support search by contract", async () => {
    const provider = new AgentBrowserProvider({ runner: async () => ({ stdout: "", exitCode: 0 }) });
    await expect(provider.search({ query: "q" })).rejects.toThrow(/search/);
  });
});
