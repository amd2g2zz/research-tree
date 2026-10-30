/** Anysearch adapter — the default bundled search provider (issue #584).

Wraps the anysearch CLI (the v1 vendored anysearch-skill v2.1.0 semantics;
revision-pinned — see the retired skill_setup manifest for the pin practice).
The CLI itself is provisioned by `rt setup` (#588) and needs an API key via
injected env; this adapter never touches credentials beyond passing the
environment through.

The command runner is injectable so tests are deterministic without the CLI;
production uses the default spawn runner.
*/

import { spawn } from "node:child_process";

import type { DataSourceProvider, ProviderDocument, ProviderManifest, ResourceRef, SearchQuery, SearchResult } from "./types.js";

export interface CommandResult {
  stdout: string;
  exitCode: number;
}

export type CommandRunner = (command: string, args: string[]) => Promise<CommandResult>;

export interface AnysearchOptions {
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

export class AnysearchProvider implements DataSourceProvider {
  readonly manifest: ProviderManifest;
  private readonly config: Record<string, unknown>;
  private readonly runner: CommandRunner;

  constructor(options: AnysearchOptions = {}) {
    this.config = options.config ?? {};
    this.runner = options.runner ?? defaultRunner;
    this.manifest = {
      name: "anysearch",
      capabilities: { search: true, fetch: false },
      kinds: ["web-search"],
      description: "general web search (default provider)",
      usage: "docs/providers/anysearch.md",
      ...options.manifest,
    };
  }

  async search(query: SearchQuery): Promise<SearchResult[]> {
    const result = await this.runner("anysearch", ["search", "--query", query.query, "--json"]);
    if (result.exitCode !== 0) {
      throw new Error(`anysearch search failed with exit code ${result.exitCode}`);
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(result.stdout);
    } catch {
      throw new Error("anysearch search returned non-JSON output");
    }
    if (!Array.isArray(parsed)) {
      throw new Error("anysearch search output must be a JSON array");
    }
    return parsed.map((entry) => {
      const record = entry as Record<string, unknown>;
      return {
        title: String(record.title ?? ""),
        url: String(record.url ?? ""),
        snippet: String(record.snippet ?? ""),
      };
    });
  }

  async fetch(ref: ResourceRef): Promise<ProviderDocument> {
    throw new Error(`anysearch does not support fetch (requested: ${ref.url}); use a fetch-capable provider`);
  }
}
