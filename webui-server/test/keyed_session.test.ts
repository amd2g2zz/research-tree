/** Keyed-session tests (issue #651): readiness probe, strategy selection,
 * pi-session contract (injected runner, CI never spawns pi), heuristic
 * fallback disclosure, explicit-kind precedence, fail-closed classification. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { HeuristicClassifier, PiSessionClassifier, pickClassifier } from "../src/classify.js";
import { readPiConfig } from "../src/pi-config.js";
import { WebUIServer } from "../src/server.js";

describe("keyed-session readiness + auto-classification (issue #651)", () => {
  it("readiness probe: no key/模型 → not ready; 齐备 → ready", () => {
    const empty = readPiConfig(mkdtempSync(join(tmpdir(), "rt-ks-empty-")));
    expect(empty.keyed_session_ready).toBe(false);
    expect(empty.follows_pi_default).toBe(true); // nothing overridden → follow pi agent

    const dir = mkdtempSync(join(tmpdir(), "rt-ks-full-"));
    // pi's REAL registry shape: models.json providers with key + models
    writeFileSync(
      join(dir, "models.json"),
      JSON.stringify({
        providers: {
          zai: {
            name: "Z",
            baseUrl: "https://api.example.com/v1",
            api: "openai-completions",
            apiKey: "sk-K",
            models: [{ id: "m-1", name: "Model One" }],
          },
        },
      }),
    );
    writeFileSync(join(dir, "models-store.json"), JSON.stringify({ default: "zai/m-1" }));
    const full = readPiConfig(dir);
    expect(full.keyed_session_ready).toBe(true);
    expect(full.models).toEqual([{ id: "zai/m-1", name: "Model One", provider: "zai" }]);
    expect(full.follows_pi_default).toBe(false);
    expect(JSON.stringify(full)).not.toContain("sk-K"); // masking intact
  });

  it("strategy selection follows readiness; heuristic is deterministic and disclosed", async () => {
    expect(pickClassifier({ ready: false }).name).toBe("heuristic");
    expect(pickClassifier({ ready: true }).name).toBe("pi-session");

    const heuristic = new HeuristicClassifier();
    expect(await heuristic.classify("或者我们换 4C8G？")).toMatchObject({
      kind: "branch",
      classified_by: "heuristic",
    });
    expect(await heuristic.classify("2C4G 应该够用吧")).toMatchObject({
      kind: "guess",
    });
    expect(await heuristic.classify("我希望越快越好")).toMatchObject({
      kind: "preference",
    });
    expect(await heuristic.classify("实测 p95 已 400ms")).toMatchObject({
      kind: "claim",
    });
  });

  it("pi-session contract: strict JSON parsed, unusable answers fail closed", async () => {
    const good = new PiSessionClassifier({
      runner: () => '好的，分类如下 {"kind":"claim"} 请查收',
    });
    expect(await good.classify("实测 p95 已 400ms")).toEqual({
      kind: "claim",
      classified_by: "pi-session",
    });

    const garbage = new PiSessionClassifier({
      runner: () => "我没有理解这句话",
    });
    await expect(garbage.classify("anything")).rejects.toThrow(/no JSON/);

    const badKind = new PiSessionClassifier({
      runner: () => '{"kind":"user-profile"}',
    });
    await expect(badKind.classify("anything")).rejects.toThrow(/unusable kind/); // fail closed, no silent reroute

    const malformed = new PiSessionClassifier({
      runner: () => "{kind: claim}",
    });
    await expect(malformed.classify("anything")).rejects.toThrow(/malformed JSON/);
  });

  it("hub: explicit kind respected (classified_by=user); omitted kind auto-classifies with disclosure", async () => {
    const ws = await connect();
    await rpc(ws, "project.create", { project_id: "pK", name: "n" });
    await rpc(ws, "project.registerTask", {
      project_id: "pK",
      task_id: "tK",
      role: "main",
    });

    const explicit = await rpc(ws, "chat.ingest", {
      task_id: "tK",
      kind: "branch",
      text: "换成 4C8G？",
    });
    expect((explicit.receipt as Record<string, unknown>).classified_by).toBe("user");

    const auto = await rpc(ws, "chat.ingest", {
      task_id: "tK",
      text: "我希望越快越好",
    }); // no kind → heuristic fallback (no key)
    expect((auto.receipt as Record<string, unknown>).classified_by).toBe("heuristic");
    expect((auto.receipt as { routed: string }).routed).toBe("slot");

    const history = await rpc(ws, "chat.history", { task_id: "tK" });
    const users = (history.messages as Array<Record<string, unknown>>).filter((m) => m.role === "user");
    expect(users.every((m) => JSON.parse(String(m.receipt_json)).classified_by !== undefined)).toBe(true);
  });

  it("hub with a keyed session: the pi-session classifier serves auto classification", async () => {
    const piDir = mkdtempSync(join(tmpdir(), "rt-ks-pi-"));
    writeFileSync(
      join(piDir, "models.json"),
      JSON.stringify({
        providers: { zai: { apiKey: "k", models: [{ id: "m-1" }] } },
      }),
    );
    writeFileSync(join(piDir, "models-store.json"), JSON.stringify({ default: "zai/m-1" }));
    const server2 = new WebUIServer({
      workspace: mkdtempSync(join(tmpdir(), "rt-ks-ws-")),
      piConfigDir: piDir,
      piRunner: () => '{"kind":"guess"}', // contract: the runner returns strict JSON
    });
    const port2 = await server2.listen();
    try {
      const ws2 = await new Promise<WebSocket>((resolve, reject) => {
        const socket = new WebSocket(`ws://127.0.0.1:${port2}/ws`);
        socket.on("open", () => resolve(socket));
        socket.on("error", reject);
      });
      const rpc2 = (method: string, params: Record<string, unknown>): Promise<Record<string, unknown>> =>
        new Promise((resolve, reject) => {
          const on = (data: unknown): void => {
            const msg = JSON.parse(String(data)) as Record<string, unknown>;
            if (msg.id === 1) {
              ws2.off("message", on);
              msg.ok === true ? resolve(msg.result as Record<string, unknown>) : reject(new Error(String(msg.error)));
            }
          };
          ws2.on("message", on);
          ws2.send(JSON.stringify({ id: 1, method, params }));
        });
      await rpc2("project.create", { project_id: "pPi", name: "n" });
      await rpc2("project.registerTask", {
        project_id: "pPi",
        task_id: "tPi",
        role: "main",
      });
      const result = await rpc2("chat.ingest", {
        task_id: "tPi",
        text: "2C4G 应该够用吧",
      });
      expect((result.receipt as Record<string, unknown>).classified_by).toBe("pi-session");
      expect((result.receipt as { routed: string }).routed).toBe("hypothesis-ledger");
      ws2.close();
    } finally {
      await server2.close();
    }
  });
});

let server: WebUIServer;
let port: number;
let nextId = 1;

beforeAll(async () => {
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-ks-main-")),
    piConfigDir: mkdtempSync(join(tmpdir(), "rt-ks-main-pi-")), // empty → heuristic fallback
  });
  port = await server.listen();
});
afterAll(async () => {
  await server.close();
});

function connect(): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    socket.on("open", () => resolve(socket));
    socket.on("error", reject);
  });
}

function rpc(ws: WebSocket, method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
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
