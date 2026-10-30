/** web_fetch adapter — direct fetch + document conversion (issue #590).

Third bundled DataSourceProvider. Covers direct network requests, downloads,
content extraction with deterministic summaries (plain text / code only), and
pdf/pptx/docx/xlsx → markdown via the markitdown CLI (Microsoft, MIT, local —
reused per the free-tooling ruling; version-pinned by #588 provisioning).

Extraction stack (all free/local):
- text/plain, code          → raw text preserved + deterministic summary
- text/html                 → @mozilla/readability → turndown → markdown
- application/pdf, office   → download → markitdown CLI → markdown

Routing: static resources route here (fast, cheap); JS-rendered pages route
to agent-browser (#587) by EVSI/cost. Failure semantics: HTTP errors, size
cap, and CLI failures are structured — never silent empty evidence. Zero paid
APIs anywhere in the stack.

The HTTP fetcher and the markitdown runner are injectable for deterministic
tests; production uses global fetch and the provisioned CLI.
*/

import { mkdtempSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";
import TurndownService from "turndown";

import type { DataSourceProvider, ProviderDocument, ProviderManifest, ResourceRef, SearchQuery, SearchResult } from "./types.js";

export interface CommandResult {
  stdout: string;
  exitCode: number;
}

export type CommandRunner = (command: string, args: string[]) => Promise<CommandResult>;

export interface ContentSummary {
  title?: string;
  /** deterministic outline: block-leading lines (plain text) */
  outline?: string[];
  /** fenced/braced code inventory with naive language detection */
  codeBlocks?: Array<{ language: string; blocks: number }>;
  lines: number;
  bytes: number;
}

export interface ExtendedProviderDocument extends ProviderDocument {
  summary?: ContentSummary;
}

export interface WebFetchOptions {
  manifest?: Partial<ProviderManifest>;
  config?: Record<string, unknown>;
  fetchFn?: typeof fetch;
  markitdownRunner?: CommandRunner;
  /** download cap in bytes (default 32 MiB) */
  maxBytes?: number;
  /** fetch timeout in ms (default 30s) */
  timeoutMs?: number;
  workspace?: string;
}

const DEFAULT_MAX_BYTES = 32 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 30_000;

function defaultMarkitdownRunner(command: string, args: string[]): Promise<CommandResult> {
  return new Promise((resolve, reject) => {
    const child = Bun_spawn(command, args);
    let stdout = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.on("error", (error: Error) => reject(error));
    child.on("close", (code: number) => resolve({ stdout, exitCode: code }));
  });
}

// node:child_process spawn (aliased to keep the import surface single)
import { spawn as Bun_spawn } from "node:child_process";

function extensionFor(url: string, contentType: string): string {
  const fromUrl = url.split("?")[0]!.split("#")[0]!;
  const dot = fromUrl.lastIndexOf(".");
  if (dot > -1 && dot > fromUrl.length - 8) {
    return fromUrl.slice(dot);
  }
  if (contentType.includes("pdf")) {
    return ".pdf";
  }
  if (contentType.includes("spreadsheet") || contentType.includes("excel")) {
    return ".xlsx";
  }
  if (contentType.includes("wordprocessing")) {
    return ".docx";
  }
  if (contentType.includes("presentation")) {
    return ".pptx";
  }
  return ".bin";
}

function looksLikeCode(body: string): boolean {
  if (/```/.test(body)) {
    return true;
  }
  const codeSignals = [/[{};]\s*$/m, /^\s*(fn |def |class |function |import |package )/m, /=>/, /\breturn\b/];
  return codeSignals.filter((signal) => signal.test(body)).length >= 2;
}

const EXTENSION_LANGUAGES: Record<string, string> = {
  rs: "rust", py: "python", ts: "typescript", tsx: "typescript", js: "javascript",
  jsx: "javascript", go: "go", rb: "ruby", java: "java", kt: "kotlin", swift: "swift",
  c: "c", h: "c", cpp: "cpp", cs: "csharp", sh: "shell", sql: "sql", md: "markdown",
};

function detectLanguage(url: string, body: string): string {
  const fromUrl = url.split("?")[0]!.split("#")[0]!;
  const dot = fromUrl.lastIndexOf(".");
  if (dot > -1) {
    const ext = fromUrl.slice(dot + 1);
    const mapped = EXTENSION_LANGUAGES[ext];
    if (mapped !== undefined) {
      return mapped;
    }
    if (/^[a-z0-9]{1,5}$/.test(ext)) {
      return ext;
    }
  }
  if (/fn |let |match |impl /.test(body)) {
    return "rust";
  }
  if (/def |import |print\(/.test(body)) {
    return "python";
  }
  return "text";
}

function summarize(body: string, url: string, contentType: string): ContentSummary {
  const lines = body.split("\n");
  const summary: ContentSummary = {
    lines: lines.length,
    bytes: Buffer.byteLength(body, "utf8"),
  };
  const titleCandidate = lines.find((line) => line.trim() !== "");
  if (titleCandidate !== undefined) {
    summary.title = titleCandidate.trim().slice(0, 200);
  }
  if (contentType.includes("markdown") || /```/.test(body)) {
    const fences = [...body.matchAll(/```([a-zA-Z0-9+#-]*)/g)];
    if (fences.length >= 2) {
      const byLanguage = new Map<string, number>();
      for (let i = 0; i + 1 < fences.length; i += 2) {
        const fence = fences[i];
        const language = fence === undefined || fence[1] === "" || fence[1] === undefined ? "text" : fence[1];
        byLanguage.set(language, (byLanguage.get(language) ?? 0) + 1);
      }
      summary.codeBlocks = [...byLanguage.entries()].map(([language, blocks]) => ({ language, blocks }));
    }
  } else if (looksLikeCode(body)) {
    summary.codeBlocks = [{ language: detectLanguage(url, body), blocks: 1 }];
    return summary;
  }
  summary.outline = lines
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .slice(0, 20);
  return summary;
}

function htmlToMarkdown(html: string): { markdown: string; title?: string } {
  const dom = new JSDOM(html);
  const title = dom.window.document.title || undefined;
  const reader = new Readability(dom.window.document.cloneNode(true) as unknown as Document);
  const article = reader.parse();
  const source = article?.content ?? dom.window.document.body.innerHTML;
  const body = new TurndownService({ headingStyle: "atx" }).turndown(source);
  const resolvedTitle = article?.title ?? title;
  // Readability consumes the h1 into article.title — put it back on top
  const markdown = resolvedTitle && !body.startsWith(`# ${resolvedTitle}`)
    ? `# ${resolvedTitle}\n\n${body}`
    : body;
  return { markdown, title: resolvedTitle };
}

export class WebFetchProvider implements DataSourceProvider {
  readonly manifest: ProviderManifest;
  private readonly config: Record<string, unknown>;
  private readonly fetchFn: typeof fetch;
  private readonly markitdownRunner: CommandRunner;
  private readonly maxBytes: number;
  private readonly timeoutMs: number;
  private readonly workspace: string;

  constructor(options: WebFetchOptions = {}) {
    this.config = options.config ?? {};
    this.fetchFn = options.fetchFn ?? fetch;
    this.markitdownRunner = options.markitdownRunner ?? defaultMarkitdownRunner;
    this.maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.workspace = options.workspace ?? tmpdir();
    this.manifest = {
      name: "web_fetch",
      capabilities: { search: false, fetch: true },
      kinds: ["web-page", "pdf", "office-doc"],
      description: "direct fetch + content extraction + pdf/office→markdown (markitdown)",
      usage: "docs/providers/web-fetch.md",
      ...options.manifest,
    };
  }

  async search(query: SearchQuery): Promise<SearchResult[]> {
    throw new Error(`web_fetch does not support search (requested: ${query.query}); use a search-capable provider`);
  }

  async fetch(ref: ResourceRef): Promise<ProviderDocument> {
    const response = await this.fetchFn(ref.url, {
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!response.ok) {
      throw new Error(`web_fetch failed: HTTP ${response.status} for ${ref.url}`);
    }
    const contentType = response.headers.get("content-type") ?? "application/octet-stream";
    const buffer = Buffer.from(await response.arrayBuffer());
    if (buffer.byteLength > this.maxBytes) {
      throw new Error(
        `web_fetch download exceeds the size cap: ${buffer.byteLength} > ${this.maxBytes} bytes for ${ref.url}`,
      );
    }

    if (contentType.includes("text/html")) {
      const { markdown, title } = htmlToMarkdown(buffer.toString("utf8"));
      return {
        url: ref.url,
        contentType: "text/markdown",
        text: markdown,
        bytes: Buffer.byteLength(markdown, "utf8"),
        summary: summarize(markdown, ref.url, "text/markdown"),
      };
    }

    const isOffice = /pdf|wordprocessing|spreadsheet|presentation|msword|officedocument/.test(contentType);
    const suffix = extensionFor(ref.url, contentType);
    if (!isOffice && !suffix.endsWith(".pdf") && !/\.(docx|xlsx|pptx|doc|xls|ppt)$/.test(suffix)) {
      const body = buffer.toString("utf8");
      return {
        url: ref.url,
        contentType: contentType.startsWith("text/") ? contentType : "text/plain",
        text: body,
        bytes: buffer.byteLength,
        summary: summarize(body, ref.url, contentType),
      };
    }

    const tempFile = join(mkdtempSync(join(tmpdir(), "rt-webfetch-")), `download${suffix}`);
    await writeFile(tempFile, buffer);
    const result = await this.markitdownRunner("markitdown", [tempFile]);
    if (result.exitCode !== 0) {
      throw new Error(`markitdown conversion failed with exit code ${result.exitCode} for ${ref.url}`);
    }
    return {
      url: ref.url,
      contentType: "text/markdown",
      text: result.stdout,
      bytes: Buffer.byteLength(result.stdout, "utf8"),
      summary: summarize(result.stdout, ref.url, "text/markdown"),
    };
  }
}
