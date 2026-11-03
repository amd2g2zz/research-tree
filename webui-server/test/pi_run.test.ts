/** Async pi runner tests (issue #670): the event loop never blocks and the
 * timeout kills hung processes with a typed error. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { runPi } from "../src/pi-run.js";
import { WebUIServer } from "../src/server.js";

describe("runPi (issue #670)", () => {
  it("resolves stdout on success", async () => {
    // runPi runs `<command> -p <prompt>` — node -p evaluates the expression
    const out = await runPi(process.execPath, "40 + 2", 10_000);
    expect(out.trim()).toBe("42");
  });

  it("timeout kills a hung process with a typed error", async () => {
    const t0 = Date.now();
    await expect(runPi(process.execPath, "setTimeout(() => {}, 30_000)", 500)).rejects.toThrow(/exited with code| terminated/);
    expect(Date.now() - t0).toBeLessThan(5_000);
  }, 10_000);

  it("spawn failure fails closed with the underlying error", async () => {
    await expect(runPi("/nonexistent/pi-binary", "x", 5_000)).rejects.toThrow(/pi spawn failed/);
  });
});

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;

beforeAll(async () => {
  const piDir = mkdtempSync(join(tmpdir(), "rt-asp-pi-"));
  writeFileSync(
    join(piDir, "models.json"),
    JSON.stringify({ providers: { deepseek: { apiKey: "k", models: [{ id: "flash" }] } } }),
  );
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-asp-")),
    piConfigDir: piDir,
    piRunner: async (_command: string, prompt: string) => {
      // simulates a 3s model call — the OLD spawnSync server froze everything
      await new Promise((r) => setTimeout(r, 3_000));
      return prompt.includes("preference|claim|guess|constraint|branch") ? '{"kind":"claim"}' : '{"reply":"回应","questions":[],"recon":null}';
    },
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

describe("server stays responsive while pi runs (issue #670)", () => {
  it("a 3s in-flight turn does not block REST reads", async () => {
    await rpc("project.create", { project_id: "pA", name: "n" });
    await rpc("project.registerTask", { project_id: "pA", task_id: "tA", role: "main" });

    const turnPromise = rpc("chat.turn", { task_id: "tA", text: "测试并发" });
    await new Promise((r) => setTimeout(r, 500)); // turn now in-flight (slow runner)

    const t0 = Date.now();
    const res = await fetch(`http://127.0.0.1:${port}/api/projects`);
    const apiMs = Date.now() - t0;
    expect(res.status).toBe(200);
    expect(apiMs).toBeLessThan(1_000); // the OLD spawnSync server blocked here for 3s+

    const result = await turnPromise;
    expect((result.reply as string)).toBe("回应");
  }, 20_000);
});
