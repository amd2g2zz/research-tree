import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ExtendedProviderDocument, WebFetchProvider } from "../src/providers/web_fetch.js";

let workspace: string;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-webfetch-"));
});

function provider(overrides: Partial<ConstructorParameters<typeof WebFetchProvider>[0]> = {}) {
  return new WebFetchProvider({
    workspace,
    markitdownRunner: async () => ({ stdout: "# Converted\n\nmarkitdown output", exitCode: 0 }),
    fetchFn: async () => new Response("not used", { status: 404 }),
    ...overrides,
  });
}

const HTML_PAGE = `<!doctype html><html><head><title>Research Tree Notes</title></head>
<body><article><h1>Research Tree Notes</h1><p>First paragraph with content.</p>
<h2>Design</h2><p>The design section body.</p></article></body></html>`;

describe("web_fetch: html and text", () => {
  it("extracts an HTML article to markdown with the title", async () => {
    const p = provider({
      fetchFn: async () => new Response(HTML_PAGE, { status: 200, headers: { "content-type": "text/html" } }),
    });
    const doc = (await p.fetch({ url: "https://example.com/notes" })) as ExtendedProviderDocument;
    expect(doc.contentType).toBe("text/markdown");
    expect(doc.text).toContain("Research Tree Notes");
    expect(doc.text).toContain("Design");
    expect(doc.summary?.title).toBe("# Research Tree Notes"); // outline lines are verbatim
  });

  it("preserves plain text with a deterministic summary", async () => {
    const body = "Research Tree Notes\n\nSection one body.\n\nSection two body.";
    const p = provider({
      fetchFn: async () => new Response(body, { status: 200, headers: { "content-type": "text/plain" } }),
    });
    const doc = (await p.fetch({ url: "https://example.com/notes.txt" })) as ExtendedProviderDocument;
    expect(doc.text).toBe(body);
    expect(doc.summary?.outline).toEqual(["Research Tree Notes", "Section one body.", "Section two body."]);
    expect(doc.summary?.lines).toBe(5);
  });

  it("summarizes code with language detection and block inventory", async () => {
    const body = 'fn main() {\n    println!("hello");\n}\n\nfn helper() -> u32 {\n    7\n}';
    const p = provider({
      fetchFn: async () => new Response(body, { status: 200, headers: { "content-type": "text/x-rust" } }),
    });
    const doc = (await p.fetch({ url: "https://example.com/main.rs" })) as ExtendedProviderDocument;
    expect(doc.text).toBe(body);
    expect(doc.summary?.codeBlocks).toEqual([{ language: "rust", blocks: 1 }]);
    expect(doc.summary?.lines).toBe(7);
  });

  it("counts fenced code blocks in markdown-ish text", async () => {
    const body = "# Demo\n\n```python\nprint(1)\n```\n\n```python\nprint(2)\n```\n";
    const p = provider({
      fetchFn: async () => new Response(body, { status: 200, headers: { "content-type": "text/plain" } }),
    });
    const doc = (await p.fetch({ url: "https://example.com/demo.md" })) as ExtendedProviderDocument;
    expect(doc.summary?.codeBlocks).toEqual([{ language: "python", blocks: 2 }]);
  });
});

describe("web_fetch: office/pdf via markitdown", () => {
  it("downloads and converts a pdf through the markitdown CLI", async () => {
    const commands: string[] = [];
    const p = provider({
      fetchFn: async () =>
        new Response(new Uint8Array([1, 2, 3]), {
          status: 200,
          headers: { "content-type": "application/pdf" },
        }),
      markitdownRunner: async (command, args) => {
        commands.push([command, ...args].join(" "));
        return { stdout: "# Converted\n\nmarkitdown output", exitCode: 0 };
      },
    });
    const doc = (await p.fetch({ url: "https://example.com/paper.pdf" })) as ExtendedProviderDocument;
    expect(doc.text).toContain("markitdown output");
    expect(doc.contentType).toBe("text/markdown");
    expect(commands[0]).toContain("markitdown");
    expect(commands[0]).toContain(".pdf");
  });

  it("raises a structured failure when markitdown fails", async () => {
    const p = provider({
      fetchFn: async () =>
        new Response(new Uint8Array([1]), { status: 200, headers: { "content-type": "application/pdf" } }),
      markitdownRunner: async () => ({ stdout: "corrupt", exitCode: 1 }),
    });
    await expect(p.fetch({ url: "https://example.com/bad.pdf" })).rejects.toThrow(/markitdown/);
  });

  it("handles office documents by extension sniffing", async () => {
    let sawSuffix = "";
    const p = provider({
      fetchFn: async () => new Response(new Uint8Array([1]), { status: 200, headers: { "content-type": "application/octet-stream" } }),
      markitdownRunner: async (_command, args) => {
        sawSuffix = args.join(" ");
        return { stdout: "# Sheet", exitCode: 0 };
      },
    });
    const doc = (await p.fetch({ url: "https://example.com/report.xlsx?token=1" })) as ExtendedProviderDocument;
    expect(sawSuffix).toContain(".xlsx");
    expect(doc.text).toContain("Sheet");
  });
});

describe("web_fetch: failure semantics", () => {
  it("raises structured failures on HTTP errors", async () => {
    const p = provider({
      fetchFn: async () => new Response("gone", { status: 404 }),
    });
    await expect(p.fetch({ url: "https://example.com/missing" })).rejects.toThrow(/404/);
  });

  it("enforces the download size cap", async () => {
    const big = "x".repeat(3 * 1024 * 1024);
    const p = provider({
      maxBytes: 1024,
      fetchFn: async () => new Response(big, { status: 200, headers: { "content-type": "text/plain" } }),
    });
    await expect(p.fetch({ url: "https://example.com/huge.txt" })).rejects.toThrow(/size cap/);
  });
});

describe("web_fetch: contract", () => {
  it("does not support search", async () => {
    const p = provider();
    await expect(p.search({ query: "q" })).rejects.toThrow(/search/);
  });

  it("declares its capabilities and kinds", () => {
    expect(provider().manifest).toMatchObject({
      name: "web_fetch",
      capabilities: { search: false, fetch: true },
      kinds: ["web-page", "pdf", "office-doc"],
    });
  });
});
