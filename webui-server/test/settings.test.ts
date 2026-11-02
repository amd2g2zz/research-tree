/** Settings write-path tests (issue #638): pi config single source — writes
 * modify pi's OWN files only, key values never surface anywhere, audit
 * records provider names only. */

import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";
import { readPiConfig } from "../src/pi-config.js";

let workspace: string;
let piDir: string;
let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;

beforeAll(async () => {
  workspace = mkdtempSync(join(tmpdir(), "rt-set-"));
  piDir = mkdtempSync(join(tmpdir(), "rt-pi-"));
  server = new WebUIServer({ workspace, piConfigDir: piDir });
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

describe("settings: pi config single source (issue #638)", () => {
  it("setProviderKey writes pi's own auth.json — verified, never echoed, audit name-only", async () => {
    const result = await rpc("config.setProviderKey", { provider: "zai", api_key: "sk-WRITE-TEST" });
    expect(result).toMatchObject({ saved: true, provider: "zai" });

    // pi's own file is the only thing modified, and the key actually landed
    const raw = JSON.parse(readFileSync(join(piDir, "auth.json"), "utf8")) as Record<string, Record<string, unknown>>;
    expect(raw.zai?.api_key).toBe("sk-WRITE-TEST");

    // the read path masks: the key never surfaces over the wire
    const summary = readPiConfig(piDir);
    expect(summary.auth_providers).toContain("zai");
    expect(JSON.stringify(summary)).not.toContain("sk-WRITE-TEST");

    // the audit event records the provider name only
    const events = server.ledgerForTests().graphEvents().filter((e) => (e.payload as Record<string, unknown>).provider === "settings");
    const target = String((events.at(-1)?.payload as Record<string, unknown>).target);
    expect(target).toBe("settings:auth:zai");
    expect(JSON.stringify(events)).not.toContain("sk-WRITE-TEST");
  });

  it("setDefaultModel writes models-store.json with write-then-read verification", async () => {
    const result = await rpc("config.setDefaultModel", { model: "glm-5.3" });
    expect(result).toMatchObject({ saved: true, default_model: "glm-5.3" });
    expect(existsSync(join(piDir, "models-store.json"))).toBe(true);
    const summary = readPiConfig(piDir);
    expect(summary.default_model).toBe("glm-5.3");
    expect(summary.models).toContain("glm-5.3");
  });

  it("invalid inputs rejected without touching files", async () => {
    await expect(rpc("config.setProviderKey", { provider: "bad name!", api_key: "k" })).rejects.toThrow(/provider/);
    await expect(rpc("config.setProviderKey", { provider: "ok", api_key: "" })).rejects.toThrow(/empty/);
    await expect(rpc("config.setDefaultModel", { model: "" })).rejects.toThrow(/empty/);
    expect(existsSync(join(piDir, "auth.json"))).toBe(true); // earlier valid write still intact
  });
});
