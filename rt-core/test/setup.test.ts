import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { runSetup, doctor } from "../src/setup/setup.js";
import { ProviderRegistry } from "../src/providers/registry.js";
import { AnysearchProvider } from "../src/providers/anysearch.js";
import { AgentBrowserProvider } from "../src/providers/agent_browser.js";

let workspace: string;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-setup-"));
});

function registryWithCliDeps(): ProviderRegistry {
  const registry = new ProviderRegistry();
  registry.register(new AnysearchProvider({
    runner: async () => ({ stdout: "[]", exitCode: 0 }),
    manifest: { usage: "docs/providers/anysearch.md" },
  }));
  registry.register(new AgentBrowserProvider({
    runner: async () => ({ stdout: "x", exitCode: 0 }),
    manifest: { usage: "docs/providers/agent-browser.md" },
  }));
  return registry;
}

describe("rt setup (idempotent)", { timeout: 30_000 }, () => {
  it("initializes the workspace and reports what it did", async () => {
    const report = await runSetup({ workspace });
    expect(report.steps).toMatchObject({ workspace: "created" });
    expect(existsSync(join(workspace, ".research-tree"))).toBe(true);
  });

  it("is idempotent — the second run reports already-initialized and changes nothing", async () => {
    await runSetup({ workspace });
    const second = await runSetup({ workspace });
    expect(second.steps).toMatchObject({ workspace: "already-initialized" });
  });

  it("provisions provider CLI dependencies with pinned expectations", async () => {
    const report = await runSetup({
      workspace,
      registry: registryWithCliDeps(),
      provisioner: async (name) => (name === "agent-browser" ? "installed" : "missing-api-key"),
    });
    const anysearch = report.providers.find((p: any) => p.name === "anysearch")!;
    expect(anysearch.status).toBe("missing-api-key");
    expect(anysearch.install_guidance).toContain("anysearch");
    const agentBrowser = report.providers.find((p: any) => p.name === "agent-browser")!;
    expect(agentBrowser.status).toBe("installed");
  });

  it("never runs global installs or credential writes without explicit confirmation", async () => {
    let confirmed = 0;
    const report = await runSetup({
      workspace,
      registry: registryWithCliDeps(),
      confirm: async (action) => {
        confirmed += 1;
        return action.kind === "global-install";
      },
      provisioner: async () => "installed",
    });
    expect(confirmed).toBeGreaterThanOrEqual(1);
    expect(report.confirmed_actions.every((a: any) => a.confirmed)).toBe(true);
  });
});

describe("rt doctor (boot readiness)", { timeout: 30_000 }, () => {
  it("reports per-provider availability, storage, mcp and pi states", async () => {
    runSetup({ workspace });
    const readiness = await doctor({
      workspace,
      registry: registryWithCliDeps(),
      checks: {
        providerCli: async (name) => (name === "agent-browser" ? "ok" : "missing"),
        mcpMountable: async () => true,
        piSession: async () => "attached",
      },
    });
    expect(readiness.storage).toBe("writable");
    expect(readiness.mcp).toBe("mountable");
    expect(readiness.pi).toBe("attached");
    expect(readiness.providers.find((p: any) => p.name === "agent-browser")!.state).toBe("ok");
    expect(readiness.providers.find((p: any) => p.name === "anysearch")!.state).toBe("missing");
    expect(readiness.overall).toBe("attention-required");
  });

  it("is fully ready when every check passes", async () => {
    runSetup({ workspace });
    const readiness = await doctor({
      workspace,
      registry: registryWithCliDeps(),
      checks: {
        providerCli: async () => "ok",
        mcpMountable: async () => true,
        piSession: async () => "attached",
      },
    });
    expect(readiness.overall).toBe("ready");
  });

  it("names a missing provider CLI with its install guidance (not a generic failure)", async () => {
    runSetup({ workspace });
    const readiness = await doctor({
      workspace,
      registry: registryWithCliDeps(),
      checks: { providerCli: async () => "missing", mcpMountable: async () => true, piSession: async () => "attached" },
    });
    const anysearch = readiness.providers.find((p: any) => p.name === "anysearch")!;
    expect(anysearch.state).toBe("missing");
    expect(anysearch.install_guidance).toContain("anysearch");
  });
});
