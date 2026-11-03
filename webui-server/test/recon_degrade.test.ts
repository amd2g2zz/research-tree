/** Recon degrade + SkillSearchProvider tests (issue #666): recon failure
 * must NOT kill the turn — the reply lands with an honest failed-recon line;
 * the skill CLI's markdown output parses into SearchResults. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";
import { parseMarkdownResults, SkillSearchProvider } from "../src/skill_search.js";

const TURN_WITH_RECON = JSON.stringify({
  reply: "想法收到，先做个市场侦查。",
  questions: ["目标客户是谁？"],
  recon: { query: "数据标注市场" },
});

class ExplodingProvider implements DataSourceProviderShape {
  readonly manifest = {
    name: "anysearch",
    capabilities: { search: true, fetch: false },
    kinds: ["web-search"],
    description: "explode",
    usage: "x",
  };
  async search(): Promise<never> {
    throw new Error("spawn anysearch ENOENT");
  }
  async fetch(): Promise<never> {
    throw new Error("not implemented");
  }
}

// structural subset to avoid importing the full port type twice
interface DataSourceProviderShape {
  manifest: { name: string; [key: string]: unknown };
  search(query: { query: string }): Promise<Array<{ title: string; url?: string; snippet?: string }>>;
  fetch(): Promise<never>;
}

const MARKDOWN = `## Search Results (2 results, 1219ms)

### 1. 2025年数据标注行业市场规模分析
- **URL**: https://www.mindflow.com.cn/NewsStd_1155.html
- 2025年数据标注行业市场规模分析 数据标注行业作为AI基石增长迅猛。

### 2. 第二条结果
- **URL**: https://example.com/2
- 摘要正文。
`;

describe("skill search provider (#666)", () => {
  it("parses the real markdown shape into SearchResults", () => {
    const results = parseMarkdownResults(MARKDOWN);
    expect(results).toHaveLength(2);
    expect(results[0]).toMatchObject({
      title: "2025年数据标注行业市场规模分析",
      url: "https://www.mindflow.com.cn/NewsStd_1155.html",
    });
    expect(results[0]?.snippet).toContain("AI基石");
    expect(results[1]?.url).toBe("https://example.com/2");
  });

  it("the real skill CLI (if present) returns parsable results", async () => {
    const provider = new SkillSearchProvider();
    if (!provider.available()) {
      return; // machine without the skill — discovery covered by unit above
    }
    const results = await provider.search({ query: "数据标注公司 2025 市场规模" });
    expect(results.length).toBeGreaterThan(0);
    expect(results[0]?.title).not.toBe("");
  });
});

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;

beforeAll(async () => {
  const piDir = mkdtempSync(join(tmpdir(), "rt-rd-pi-"));
  writeFileSync(
    join(piDir, "models.json"),
    JSON.stringify({ providers: { deepseek: { apiKey: "k", models: [{ id: "flash" }] } } }),
  );
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-rd-")),
    piConfigDir: piDir,
    piRunner: (_command: string, prompt: string) =>
      prompt.includes("preference|claim|guess|constraint|branch")
        ? '{"kind":"preference"}'
        : TURN_WITH_RECON,
    provider: new ExplodingProvider(), // recon provider always fails
  });
  port = await server.listen();
});
afterAll(async () => {
  await server.close();
  ws?.close();
});

beforeEach(async () => {
  ws?.close();
  ws = await new Promise<WebSocket>((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    socket.on("open", () => resolve(socket));
    socket.on("error", reject);
  });
});

function rpc(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const onMessage = (data: unknown): void => {
      const msg = JSON.parse(String(data)) as Record<string, unknown>;
      if (msg.id === id) {
        ws.off("message", onMessage);
        if (msg.ok === true) {
          resolve(msg.result as Record<string, unknown>);
        } else {
          reject(new Error(String(msg.error)));
        }
      }
    };
    ws.on("message", onMessage);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

describe("recon degradation (#666)", () => {
  it("provider failure degrades: the reply still lands with an honest failed-recon line", async () => {
    await rpc("project.create", { project_id: "pD", name: "n" });
    await rpc("project.registerTask", { project_id: "pD", task_id: "tD", role: "main" });
    const result = await rpc("chat.turn", { task_id: "tD", text: "我想开个数据标注公司" });
    expect((result.reply as string)).toContain("市场侦查"); // the reply SURVIVED
    expect(result.recon_error).toContain("ENOENT");
    expect((result.recon_results as unknown[])).toHaveLength(0);

    // the transcript carries the honest failed-recon line
    const history = (await rpc("chat.history", { task_id: "tD" })).messages as Array<Record<string, unknown>>;
    const reconRow = history.find((m) => m.kind === "recon");
    expect(String(reconRow?.text)).toContain("前期侦查失败");
    expect(String(reconRow?.text)).toContain("回应不受影响");
  });
});
