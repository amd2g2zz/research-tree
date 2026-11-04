/** Mindmap RPC tests (issue #683): generate (quote 回查溯源), draft editing,
 * confirm → mechanical stages → research phase. Runner injected (CI never
 * spawns pi). */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";
import { mechanicalPlan, parseMindmap } from "../src/mindmap.js";

const TRANSCRIPT = [
  { seq: 1, role: "user", kind: "preference", text: "我想开个数据标注公司", created_at: "t" },
  { seq: 2, role: "user", kind: "guess", text: "预算 50 万以内，5 人团队", created_at: "t" },
];
const MINDMAP_JSON = JSON.stringify({
  root: {
    text: "数据标注公司如何冷启动并验证商业模型",
    children: [
      { text: "限制条件", children: [{ text: "预算 50 万", quote: "预算 50 万以内" }, { text: "5 人团队", quote: "5 人团队" }] },
      { text: "任务背景", children: [{ text: "AI 数据需求增长", quote: "数据标注" }] },
      { text: "调研目标", children: [{ text: "冷启动路径验证", quote: "开个数据标注公司" }] },
    ],
  },
});

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;

beforeAll(async () => {
  const piDir = mkdtempSync(join(tmpdir(), "rt-mm-pi-"));
  writeFileSync(
    join(piDir, "models.json"),
    JSON.stringify({ providers: { deepseek: { apiKey: "k", models: [{ id: "flash" }] } } }),
  );
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-mm-")),
    piConfigDir: piDir,
    piRunner: () => MINDMAP_JSON,
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

describe("mindmap full-canvas flow (issue #683)", () => {
  it("unit: quotes map back to the transcript; unmapped counted; depth capped", () => {
    const parsed = parseMindmap(MINDMAP_JSON, TRANSCRIPT);
    expect(parsed.dropped).toBe(0);
    expect(parsed.tree.root.text).toContain("冷启动");
    expect(parsed.tree.root.children).toHaveLength(3);
    const branch = parsed.tree.root.children[0]!;
    expect(branch.children[0]?.quote).toBe("预算 50 万以内"); // mapped to msg 2
    const plan = mechanicalPlan(parsed.tree);
    expect(plan.length).toBeGreaterThan(2); // leaves → stages
  });

  it("full flow: generate → draft editable → confirm → stages registered → research phase", async () => {
    await rpc("project.create", { project_id: "pM", name: "思维导图" });
    await rpc("project.registerTask", { project_id: "pM", task_id: "tM", role: "main" });
    await rpc("chat.ingest", { task_id: "tM", kind: "preference", text: "我想开个数据标注公司" });
    await rpc("chat.ingest", { task_id: "tM", kind: "guess", text: "预算 50 万以内，5 人团队" });

    const gen = await rpc("mindmap.generate", { task_id: "tM" });
    expect(gen.dropped).toBe(0); // quotes mapped back
    const root = (gen.tree as { root: { text: string; children: Array<{ text: string }> } }).root;
    expect(root.children.length).toBeGreaterThanOrEqual(3); // 限制条件/任务背景/调研目标

    // draft editing: rename a depth-1 node
    const tree = gen.tree as { root: { children: Array<{ id: string; text: string }> } };
    const nodeId = tree.root.children[0]!.id;
    const edited = await rpc("mindmap.editNode", { task_id: "tM", action: "rename", node_id: nodeId, text: "硬性限制条件" });
    expect(((edited.tree as { root: { children: Array<{ text: string }> } }).root.children[0] as { text: string }).text).toBe("硬性限制条件");

    // confirm freezes the tree, registers leaf stages, walks to research
    const confirmed = await rpc("mindmap.confirm", { task_id: "tM" });
    expect(confirmed.confirmed).toBe(true);
    expect(Number(confirmed.stages)).toBeGreaterThan(0);
    expect(confirmed.phase).toBe("research");

    // post-confirm editing refused (major pivot)
    await expect(rpc("mindmap.editNode", { task_id: "tM", action: "rename", node_id: nodeId, text: "x" })).rejects.toThrow(
      /major pivot/,
    );
  });

  it("fail-closed without a keyed session", async () => {
    const cold = new WebUIServer({ workspace: mkdtempSync(join(tmpdir(), "rt-mm-cold-")), piConfigDir: mkdtempSync(join(tmpdir(), "rt-mm-cold-pi-")) });
    const coldPort = await cold.listen();
    const coldWs = await new Promise<WebSocket>((resolve, reject) => {
      const s = new WebSocket(`ws://127.0.0.1:${coldPort}/ws`);
      s.on("open", () => resolve(s));
      s.on("error", reject);
    });
    await rpcOn(coldWs, "project.create", { project_id: "pC", name: "n" });
    await rpcOn(coldWs, "project.registerTask", { project_id: "pC", task_id: "tC", role: "main" });
    await expect(rpcOn(coldWs, "mindmap.generate", { task_id: "tC" })).rejects.toThrow(/keyed session not ready/);
    coldWs.close();
    await cold.close();
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
