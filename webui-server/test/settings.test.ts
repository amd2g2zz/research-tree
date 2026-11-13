/** Settings write-path tests (#638/#655): pi config single source — writes
 * modify pi's OWN models.json provider registry (schema-compatible upsert),
 * key values never surface anywhere, audit records provider names only. */

import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { readPiConfig } from "../src/pi-config.js";
import { WebUIServer } from "../src/server.js";

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

describe("settings: pi config single source (#638/#655)", () => {
  it("setProviderKey upserts pi's own models.json provider — verified, never echoed, audit name-only", async () => {
    const result = await rpc("config.setProviderKey", {
      provider: "zai",
      api_key: "sk-WRITE-TEST",
      baseUrl: "https://api.z.ai/v1",
      model_id: "glm-5.3",
    });
    expect(result).toMatchObject({ saved: true, provider: "zai" });

    // pi's own models.json is the only thing modified, schema-compatible
    const raw = JSON.parse(readFileSync(join(piDir, "models.json"), "utf8")) as {
      providers: Record<string, { apiKey: string; baseUrl: string; models: Array<{ id: string }> }>;
    };
    expect(raw.providers.zai?.apiKey).toBe("sk-WRITE-TEST");
    expect(raw.providers.zai?.baseUrl).toBe("https://api.z.ai/v1");
    expect(raw.providers.zai?.models.some((m) => m.id === "glm-5.3")).toBe(true);

    // the read path masks: the key never surfaces over the wire
    const summary = readPiConfig(piDir);
    expect(summary.auth_providers).toContain("zai");
    expect(summary.keyed_session_ready).toBe(true); // key + model
    expect(JSON.stringify(summary)).not.toContain("sk-WRITE-TEST");

    // the audit event records the provider name only
    const events = server
      .ledgerForTests()
      .graphEvents()
      .filter((e) => (e.payload as Record<string, unknown>).provider === "settings");
    const target = String((events.at(-1)?.payload as Record<string, unknown>).target);
    expect(target).toBe("settings:auth:zai");
    expect(JSON.stringify(events)).not.toContain("sk-WRITE-TEST");
  });

  it("setDefaultModel writes the override marker; without it the product follows pi agent's default", async () => {
    // no override yet → follows pi default
    expect(readPiConfig(piDir).follows_pi_default).toBe(true);
    const result = await rpc("config.setDefaultModel", {
      model: "zai/glm-5.3",
    });
    expect(result).toMatchObject({ saved: true, default_model: "zai/glm-5.3" });
    expect(existsSync(join(piDir, "models-store.json"))).toBe(true);
    const summary = readPiConfig(piDir);
    expect(summary.default_model).toBe("zai/glm-5.3");
    expect(summary.follows_pi_default).toBe(false);
  });

  it("invalid inputs rejected without touching files", async () => {
    await expect(rpc("config.setProviderKey", { provider: "bad name!", api_key: "k" })).rejects.toThrow(/provider/);
    await expect(rpc("config.setProviderKey", { provider: "ok", api_key: "" })).rejects.toThrow(/empty/);
    await expect(rpc("config.setDefaultModel", { model: "" })).rejects.toThrow(/empty/);
    expect(existsSync(join(piDir, "models.json"))).toBe(true); // earlier valid write still intact
  });
});
