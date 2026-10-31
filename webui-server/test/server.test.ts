/** WebUI spike integration (issue #632): the browser round, simulated by the
 * exact WS/REST traffic the frontend issues — one full research round driven
 * end-to-end against a real ledger. LLM work stays at the pi boundary (the
 * engine walk is #579 headless machinery; CI runs the mock boundary per the
 * #607 precedent, the real pi session drive was proven in #606). */

import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";
import { readPiConfig } from "../src/pi-config.js";

const SOURCE = { kind: "chat-message" as const, ref: "msg:1", quote: "2C4G 越快上越好" };
const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [{ text: "2C4G is a guess", source: SOURCE, hardness: "guessed" }],
  background: [{ text: "pilot feedback", source: SOURCE }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] }],
  claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
};
const PLAN = {
  plan_id: "plan-webui",
  stages: [{ id: "s1", title: "recon", claim_ids: [], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
};

let workspace: string;
let server: WebUIServer;
let port: number;
let ws: WebSocket;
let engineEvents: Array<Record<string, unknown>>;
let nextId = 1;

beforeAll(async () => {
  workspace = mkdtempSync(join(tmpdir(), "rt-webui-"));
  server = new WebUIServer({ workspace });
  port = await server.listen();
});
afterAll(async () => {
  await server.close();
  ws?.close();
});

beforeEach(async () => {
  engineEvents = [];
  ws?.close();
  ws = await new Promise<WebSocket>((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    socket.on("open", () => resolve(socket));
    socket.on("error", reject);
  });
  ws.on("message", (data) => {
    const msg = JSON.parse(String(data)) as Record<string, unknown>;
    if (msg.event === "engine") {
      engineEvents.push(msg.line as Record<string, unknown>);
    }
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

async function rest(path: string): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await fetch(`http://127.0.0.1:${port}${path}`);
  return { status: res.status, body: (await res.json()) as Record<string, unknown> };
}

describe("webui spike (issue #632)", () => {
  it("pi config is read from pi's own directory — provider names only, key values never surface", () => {
    const dir = mkdtempSync(join(tmpdir(), "rt-piconf-"));
    writeFileSync(join(dir, "models-store.json"), JSON.stringify({ models: ["glm-5.3", "glm-air"], default: "glm-air" }));
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "auth.json"), JSON.stringify({ "zai": { api_key: "sk-SUPER-SECRET" }, openai: {} }));
    const summary = readPiConfig(dir);
    expect(summary.present).toBe(true);
    expect(summary.default_model).toBe("glm-air");
    expect(summary.models).toEqual(["glm-5.3", "glm-air"]);
    expect(summary.auth_providers).toEqual(["zai", "openai"]); // names only
    expect(JSON.stringify(summary)).not.toContain("sk-SUPER-SECRET"); // masking red line
  });

  it("one full research round driven over WS/REST: project → chat → decompose → sign → commit → vitals live", async () => {
    await rpc("project.create", { project_id: "p1", name: "2C4G 部署可行性" });
    await rpc("project.registerTask", { project_id: "p1", task_id: "t-main", role: "main" });

    const before = await rest("/api/projects/p1/vitals");
    expect(before.body).toMatchObject({ research_lines: 1, latest: null });

    // the chat hub: three routed utterances (the browser sends what the user typed)
    const preference = await rpc("chat.ingest", { task_id: "t-main", kind: "preference", text: "2C4G 越快上越好" });
    expect(preference.routed).toBe("slot");
    const guess = await rpc("chat.ingest", { task_id: "t-main", kind: "guess", text: "2C4G 够用了吧", hardness: "guessed" });
    expect(guess.routed).toBe("hypothesis-ledger");
    const branch = await rpc("chat.ingest", { task_id: "t-main", kind: "branch", text: "或者我们换 4C8G？" });
    expect(branch.routed).toBe("parking-lot");

    // research.launch = the decompose-confirm-sign-commit walk (#579 machinery)
    const launch = await rpc("research.launch", {
      task_id: "t-main",
      pre_signed: { verdict: "GO", summary: "2C4G 可行（webui spike）" },
      steps: [
        { event: "open-draft", snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] }, base_v: null },
        { event: "attach", decomposition: EXTRACTION, decomposition_id: "dc-1", plan: PLAN },
        { event: "confirm" },
        { event: "sign" },
        { event: "research-completed" },
      ],
    });
    expect(launch.outcome).toBe("success");
    expect(engineEvents.length).toBeGreaterThan(3); // engine events streamed to the socket

    // morning state: vitals show the committed version — the home page updates live
    const after = await rest("/api/projects/p1/vitals");
    expect(after.body.research_lines).toBe(1);
    const latest = after.body.latest as { v: number; verdict: string; commit_hash: string };
    expect(latest).toMatchObject({ v: 0, verdict: "GO" });
    expect(latest.commit_hash).toHaveLength(64);

    const projects = await rest("/api/projects");
    expect((projects.body.projects as Array<Record<string, unknown>>)[0]).toMatchObject({ project_id: "p1", status: "active" });
  });

  it("engine-side errors surface verbatim over RPC (typed, not swallowed)", async () => {
    await expect(rpc("chat.ingest", { task_id: "t2", kind: "nonsense" })).rejects.toThrow(/utterance kind/);
    await expect(rest("/api/projects/ghost/vitals")).resolves.toMatchObject({ status: 404 });
    await expect(rpc("project.registerTask", { project_id: "ghost", task_id: "t9", role: "main" })).rejects.toThrow(/unknown project/);
  });
});
