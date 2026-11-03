/** Real-flow tests (issue #655): the REAL usable path — chat transcript →
 * pi extraction (quotes mapped back to the transcript, 溯源律 drops the
 * rest) → mechanical plan → research.start registers the DAG → human
 * freeze signs the verdict. No fixtures reach the browser path. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";
import { readPiConfig } from "../src/pi-config.js";
import { extractionPrompt, parseExtraction, mechanicalPlan } from "../src/real-flow.js";

const TRANSCRIPT = [
  { seq: 1, role: "user", kind: "preference", text: "2C4G 越快上越好", created_at: "t" },
  { seq: 2, role: "user", kind: "guess", text: "2C4G 应该够用吧", created_at: "t" },
  { seq: 3, role: "user", kind: "claim", text: "实测 p95 已经 400ms", created_at: "t" },
  { seq: 4, role: "rt", kind: "receipt", text: "→ 假设账本", created_at: "t" },
];

describe("real-flow units (issue #655)", () => {
  it("extraction prompt carries the transcript and demands strict JSON", () => {
    const prompt = extractionPrompt(TRANSCRIPT);
    expect(prompt).toContain("[1] 2C4G 越快上越好");
    expect(prompt).toContain("[3] 实测 p95 已经 400ms");
    expect(prompt).toContain("quote");
    expect(prompt).not.toContain("→ 假设账本"); // rt receipts are not user words
  });

  it("parseExtraction maps quotes back to transcript messages (溯源律); unmapped quotes are dropped downstream", () => {
    const stdout = JSON.stringify({
      requirements: [{ text: "上得快", quote: "越快上越好" }],
      constraints: [{ text: "编造约束", quote: "这句话不在对话里" }],
      background: [],
      intents: [{ text: "要快", quote: "越快上越好" }],
      refusals: [],
      difficulties: [{ text: "内存顶", quote: "应该够用吧", kill_candidates: ["c-mob"] }],
      claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM" }],
    });
    const extraction = parseExtraction(stdout, TRANSCRIPT);
    expect(extraction.requirements?.[0]?.source).toMatchObject({ ref: "msg:1", quote: "越快上越好" });
    expect(extraction.constraints?.[0]?.source).toBeUndefined(); // unmapped quote keeps no provenance
    // parseDecomposition honestly drops the unmapped one
    const parsed = parseDecompositionLocal(extraction);
    expect(parsed.dropped).toBe(1);
    expect(parsed.elements.constraints).toHaveLength(0);
  });

  it("malformed extraction fails closed", () => {
    expect(() => parseExtraction("我没有理解这句话", TRANSCRIPT)).toThrow(/no JSON/);
    expect(() => parseExtraction('{"requirements":broken}', TRANSCRIPT)).toThrow(/malformed JSON/);
  });

  it("mechanical plan: one stage per claims_preview entry, no LLM", () => {
    const plan = mechanicalPlan({
      claims_preview: [
        { id: "c-mob", text: "2C4G suffices" },
        { id: "c-p95", text: "p95 acceptable" },
      ],
    });
    expect(plan.stages.map((s) => s.id)).toEqual(["stage-c-mob", "stage-c-p95"]);
    expect(plan.stages.every((s) => s.claim_ids.length === 1)).toBe(true);
    expect(plan.budget.capMs).toBe(12 * 3600 * 1000); // 12h invariant
  });
});

// local import shim to avoid a second ledger fixture here
import { parseDecomposition as parseDecompositionLocal } from "../../rt-core/src/decomposition/engine.js";

// ---------------------------------------------------------------- server flow

const SOURCE_QUOTE = "2C4G 越快上越好";
const EXTRACTION_JSON = JSON.stringify({
  requirements: [{ text: "deploy fast", quote: SOURCE_QUOTE }],
  constraints: [{ text: "2C4G is the box", quote: SOURCE_QUOTE, hardness: "hard" }],
  background: [{ text: "pilot feedback", quote: SOURCE_QUOTE }],
  intents: [{ text: "ship fast", quote: SOURCE_QUOTE }],
  refusals: [],
  difficulties: [{ text: "memory ceiling", quote: SOURCE_QUOTE, kill_candidates: ["c-mob"] }],
  claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
});

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;

beforeAll(async () => {
  const piDir = mkdtempSync(join(tmpdir(), "rt-rf-pi-"));
  writeFileSync(
    join(piDir, "models.json"),
    JSON.stringify({ providers: { deepseek: { apiKey: "k", baseUrl: "https://api.deepseek.com/v1", models: [{ id: "deepseek-flash" }] } } }),
  );
  writeFileSync(join(piDir, "models-store.json"), JSON.stringify({ default: "deepseek/deepseek-flash" }));
  expect(readPiConfig(piDir).keyed_session_ready).toBe(true);
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-rf-")),
    piConfigDir: piDir,
    piRunner: () => EXTRACTION_JSON, // contract: the injected runner stands in for pi
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

describe("real server flow: chat → extraction → confirm → start → freeze (#655)", () => {
  it("fail-closed without a keyed session; full real walk with one", async () => {
    // not-ready server: fromChat refuses honestly
    const cold = new WebUIServer({ workspace: mkdtempSync(join(tmpdir(), "rt-rf-cold-")), piConfigDir: mkdtempSync(join(tmpdir(), "rt-rf-cold-pi-")) });
    const coldPort = await cold.listen();
    const coldWs = await new Promise<WebSocket>((resolve, reject) => {
      const s = new WebSocket(`ws://127.0.0.1:${coldPort}/ws`);
      s.on("open", () => resolve(s));
      s.on("error", reject);
    });
    await rpcOn(coldWs, "project.create", { project_id: "pC", name: "n" });
    await rpcOn(coldWs, "project.registerTask", { project_id: "pC", task_id: "tC", role: "main" });
    await rpcOn(coldWs, "chat.ingest", { task_id: "tC", kind: "preference", text: "2C4G 越快上越好" });
    await expect(rpcOn(coldWs, "decompose.fromChat", { task_id: "tC" })).rejects.toThrow(/keyed session not ready/);
    coldWs.close();
    await cold.close();

    // keyed server: talk → extract (pi via injected runner) → confirm → start → freeze
    await rpc("project.create", { project_id: "pR", name: "真流程项目" });
    await rpc("project.registerTask", { project_id: "pR", task_id: "tR", role: "main" });
    await rpc("chat.ingest", { task_id: "tR", kind: "preference", text: SOURCE_QUOTE });
    await rpc("chat.ingest", { task_id: "tR", kind: "claim", text: "实测 p95 已经 400ms" });

    const draft = await rpc("decompose.fromChat", { task_id: "tR", refusals_note: "none" });
    expect(draft.dropped).toBe(0); // every quote maps back to the transcript
    expect((draft.checklist as { complete: boolean }).complete).toBe(true);

    await rpc("decompose.confirm", { task_id: "tR", decomposition_id: "dc-tR" });
    const statusPre = await rpc("task.status", { task_id: "tR" });
    expect(statusPre.phase).toBe("chat"); // confirm keeps chat; research.start moves it

    const start = await rpc("research.start", { task_id: "tR" });
    expect(start.phase).toBe("research");
    expect(Number(start.stages)).toBe(1); // one claim → one stage (mechanical)
    const stages = server
      .ledgerForTests()
      .connection.prepare("SELECT stage_id, status FROM parallel_stages")
      .all() as Array<Record<string, unknown>>;
    expect(stages.length).toBe(1);

    // 人工裁决门: freeze signs the verdict, v0 lands, phase returns to chat
    const frozen = await rpc("research.freeze", { task_id: "tR", verdict: "GO", summary: "人工签署 GO" });
    expect(frozen).toMatchObject({ committed: true, verdict: "GO" });
    expect(String(frozen.commit_hash)).toHaveLength(64);
    const statusPost = await rpc("task.status", { task_id: "tR" });
    expect(statusPost.phase).toBe("chat"); // freezeTask lands back at chat
    expect((statusPost.latest as Record<string, unknown>)).toMatchObject({ v: 0, verdict: "GO" });

    // bad verdict refused
    await expect(rpc("research.freeze", { task_id: "tR", verdict: "MAYBE" })).rejects.toThrow(/verdict must be one of/);
  });
});

function rpcOn(ws: WebSocket, method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const id = Date.now() + Math.random();
  return new Promise((resolve, reject) => {
    const on = (data: unknown): void => {
      const msg = JSON.parse(String(data)) as Record<string, unknown>;
      if (msg.id === id) {
        ws.off("message", on);
        msg.ok === true ? resolve(msg.result as Record<string, unknown>) : reject(new Error(String(msg.error)));
      }
    };
    ws.on("message", on);
    ws.send(JSON.stringify({ id, method, params }));
  });
}
