/** SkillSearchProvider (issue #666): the vendored anysearch skill CLI as a
 * real DataSourceProvider.

The anysearch CLI ships as the skill scripts (~/.agents/skills/anysearch/
scripts/anysearch_cli.js) — **positional query, markdown output** — which is
not the JSON-on-PATH form AnysearchProvider assumes, and the python variant
needs `requests` (often absent). This provider spawns the node CLI directly
(`search <query> --max_results N`) and parses its markdown result blocks
into SearchResult[].

Discovery order (server default): RT_ANYSEARCH_CLI env →
~/.agents/skills/anysearch/scripts/anysearch_cli.js → null (caller falls
back to AnysearchProvider).
*/

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import type { DataSourceProvider, ProviderManifest, SearchQuery, SearchResult } from "../../rt-core/src/providers/types.js";

export function discoverSkillCli(): string | null {
  const fromEnv = process.env.RT_ANYSEARCH_CLI;
  if (fromEnv !== undefined && fromEnv !== "" && existsSync(fromEnv)) {
    return fromEnv;
  }
  const skill = join(homedir(), ".agents", "skills", "anysearch", "scripts", "anysearch_cli.js");
  return existsSync(skill) ? skill : null;
}

export class SkillSearchProvider implements DataSourceProvider {
  readonly manifest: ProviderManifest;
  private readonly cliPath: string;
  private readonly nodeBin: string;

  constructor(options: { cliPath?: string; nodeBin?: string } = {}) {
    this.cliPath = options.cliPath ?? discoverSkillCli() ?? "";
    this.nodeBin = options.nodeBin ?? process.execPath;
    this.manifest = {
      name: "anysearch",
      capabilities: { search: true, fetch: false },
      kinds: ["web-search"],
      description: "general web search (vendored anysearch skill CLI)",
      usage: "docs/providers/anysearch.md",
    };
  }

  available(): boolean {
    return this.cliPath !== "" && existsSync(this.cliPath);
  }

  async search(query: SearchQuery): Promise<SearchResult[]> {
    if (!this.available()) {
      throw new Error("anysearch skill CLI not found (RT_ANYSEARCH_CLI)");
    }
    const stdout = await new Promise<string>((resolve, reject) => {
      const child = spawn(this.nodeBin, [this.cliPath, "search", query.query, "--max_results", "5"], { timeout: 120_000 });
      let out = "";
      child.stdout?.on("data", (chunk) => {
        out += String(chunk);
      });
      child.on("error", reject);
      child.on("close", (code: number | null) => {
        if (code === 0) {
          resolve(out);
        } else {
          reject(new Error(`anysearch skill CLI exited with code ${code}`));
        }
      });
    });
    return parseMarkdownResults(stdout);
  }

  async fetch(): Promise<never> {
    throw new Error("SkillSearchProvider does not implement fetch");
  }
}

/** Parse the CLI's markdown shape:
 * ### 1. <title>
 * - **URL**: <url>
 * <snippet lines…>
 */
export function parseMarkdownResults(stdout: string): SearchResult[] {
  const results: SearchResult[] = [];
  const blocks = stdout.split(/^### /m).slice(1);
  for (const block of blocks) {
    const titleMatch = /^\d+\.\s*(.+)$/m.exec(block);
    if (titleMatch === null || titleMatch[1] === undefined) {
      continue;
    }
    const urlMatch = /- \*\*URL\*\*: (\S+)/.exec(block);
    const bodyStart = block.indexOf("\n", urlMatch !== null ? urlMatch.index : 0);
    const snippet = (bodyStart === -1 ? "" : block.slice(bodyStart + 1))
      .split("\n### ")[0]?.trim().slice(0, 400) ?? "";
    results.push({
      title: titleMatch[1]!.trim(),
      url: urlMatch !== null ? urlMatch[1]! : "",
      snippet,
    });
  }
  return results;
}
