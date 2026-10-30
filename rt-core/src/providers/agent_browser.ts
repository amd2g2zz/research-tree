/** Agent-browser adapter — the second bundled provider (issue #587).

Covers **rendered-web fetch**: pages whose content only materializes after JS
execution, or that need interaction/login state. Wraps the agent-browser CLI
(Rust + Chrome CDP, no Playwright dependency; version pinned at provisioning
by #588 — 0.31.1 as of 2026-10-30).

Fetch strategy: `read <url>` (agent-readable full text) first; empty output
falls back to `open <url>` + `snapshot` (a11y tree) for interaction-gated
pages. Headless Chromium in CI/unattended runs. Empty extractions and CLI
failures are structured provider failures — never a silent empty document.

The command runner is injectable for deterministic tests; production uses the
default spawn runner.
*/

import { spawn } from "node:child_process";

import type { DataSourceProvider, ProviderDocument, ProviderManifest, ResourceRef, SearchQuery, SearchResult } from "./types.js";

export interface CommandResult {
  stdout: string;
  exitCode: number;
}

export type CommandRunner = (command: string, args: string[]) => Promise<CommandResult>;

export interface AgentBrowserOptions {
  manifest?: Partial<ProviderManifest>;
  config?: Record<string, unknown>;
  runner?: CommandRunner;
}

function defaultRunner(command: string, args: string[]): Promise<CommandResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { shell: false });
    let stdout = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.on("error", (error: Error) => reject(error));
    child.on("close", (code: number) => resolve({ stdout, exitCode: code }));
  });
}

export class AgentBrowserProvider implements DataSourceProvider {
  readonly manifest: ProviderManifest;
  private readonly config: Record<string, unknown>;
  private readonly runner: CommandRunner;

  constructor(options: AgentBrowserOptions = {}) {
    this.config = options.config ?? {};
    this.runner = options.runner ?? defaultRunner;
    this.manifest = {
      name: "agent-browser",
      capabilities: { search: false, fetch: true },
      kinds: ["web-rendered"],
      description: "browser-rendered page fetch via the agent-browser CLI",
      usage: "docs/providers/agent-browser.md",
      ...options.manifest,
    };
  }

  async search(query: SearchQuery): Promise<SearchResult[]> {
    throw new Error(`agent-browser does not support search (requested: ${query.query}); use a search-capable provider`);
  }

  async fetch(ref: ResourceRef): Promise<ProviderDocument> {
    const read = await this.runner("agent-browser", ["read", ref.url]);
    if (read.exitCode !== 0) {
      throw new Error(`agent-browser fetch failed with exit code ${read.exitCode}`);
    }
    if (read.stdout.trim() === "") {
      // interaction-gated page: open it, then take an accessibility snapshot
      const open = await this.runner("agent-browser", ["open", ref.url]);
      if (open.exitCode !== 0) {
        throw new Error(`agent-browser fetch failed with exit code ${open.exitCode}`);
      }
      const snapshot = await this.runner("agent-browser", ["snapshot"]);
      if (snapshot.exitCode !== 0) {
        throw new Error(`agent-browser fetch failed with exit code ${snapshot.exitCode}`);
      }
      return this.document(ref, snapshot.stdout);
    }
    return this.document(ref, read.stdout);
  }

  private document(ref: ResourceRef, text: string): ProviderDocument {
    if (text.trim() === "") {
      throw new Error(`agent-browser empty extraction for ${ref.url} (bot wall or empty page)`);
    }
    return {
      url: ref.url,
      contentType: "text/markdown",
      text,
      bytes: Buffer.byteLength(text, "utf8"),
    };
  }
}
