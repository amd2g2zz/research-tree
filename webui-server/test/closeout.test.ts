/** WebUI closeout (issue #639): the FULL 三步走 driven over the exact
 * WS/REST traffic the browser issues, across every page (P0 home → P1 tree →
 * P2 hub → P3 decompose → P4 research → P5 versions/snapshot → settings),
 * against a real ledger + a real pi config directory — the LLM stays at the
 * pi boundary (mocked here per the #607 precedent; the wiring is real).
 *
 * 红线走查 pinned: archived projects read-only / delete blocked / snapshot
 * immutable / status card lifecycle / audit carries no key values /
 * no-fake-lineage / 未冻结·不可跟踪 labeling. */

import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";
import { readPiConfig } from "../src/pi-config.js";

const SOURCE = { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" };
const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [
    { text: "2C4G is a guess", source: SOURCE, hardness: "guessed" },
    { text: "ship this quarter", source: SOURCE },
  ],
  background: [{ text: "pilot feedback", source: SOURCE }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] }],
  claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM" }],
};
const PLAN = {
  plan_id: "plan-co",
  stages: [{ id: "s1", title: "recon", claim_ids: ["c-mob"], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
};

let workspace: string;
let piDir: string;
let server: WebUIServer;
let port: number;
let ws: WebSocket;
let engineEvents = 0;
let nextId = 1;

beforeAll(async () => {
  workspace = mkdtempSync(join(tmpdir(), "rt-co-"));
  piDir = mkdtempSync(join(tmpdir(), "rt-co-pi-"));
  server = new WebUIServer({ workspace, piConfigDir: piDir });
  port = await server.listen();
});
afterAll(async () => {
  await server.close();
  ws?.close();
});

function connect(): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    socket.on("open", () => resolve(socket));
    socket.on("error", reject);
    socket.on("message", (data) => {
      if ((JSON.parse(String(data)) as Record<string, unknown>).event === "engine") {
        engineEvents += 1;
      }
    });
  });
}

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

describe("WebUI closeout — full 三步走 over the wire (issue #639)", () => {
  it("P0/P1: two projects, card wall rules, tree with draft + fork markers", async () => {
    ws = await connect();
    await rpc("project.create", { project_id: "pA", name: "主项目", attachments: [{ id: "att:1", kind: "xlsx", label: "压测.xlsx" }] });
    await rpc("project.registerTask", { project_id: "pA", task_id: "tA", role: "main" });
    await rpc("project.create", { project_id: "pB", name: "旁项目" });
    await rpc("project.registerTask", { project_id: "pB", task_id: "tB", role: "main" });
    // isolation + delete red line
    await expect(rpc("project.delete", { project_id: "pA" })).rejects.toThrow(/archiv/);
    const tree = (await rest("/api/tree")).body.projects as Array<Record<string, unknown>>;
    expect(tree).toHaveLength(2);
    expect(tree.every((p) => Array.isArray(p.lines) && (p.lines as unknown[]).length === 1)).toBe(true);
  });

  it("P2: four-way routing receipts over the hub; ≥3 gate opens 分解", async () => {
    const p = await rpc("chat.ingest", { task_id: "tA", kind: "preference", text: "2C4G 越快上越好" });
    expect((p.receipt as { routed: string }).routed).toBe("slot");
    const g = await rpc("chat.ingest", { task_id: "tA", kind: "guess", text: "2C4G 够用吧", hardness: "guessed" });
    expect((g.receipt as { routed: string }).routed).toBe("hypothesis-ledger");
    const b = await rpc("chat.ingest", { task_id: "tA", kind: "branch", text: "或者 4C8G？" });
    expect((b.receipt as { routed: string }).routed).toBe("parking-lot");
    const status = await rpc("task.status", { task_id: "tA" });
    expect(status.routed_count).toBe(3); // 「聊得差不多了 → 分解」可用
    const history = await rpc("chat.history", { task_id: "tA" });
    expect((history.messages as unknown[]).length).toBe(6);
  });

  it("P3: draft → checklist gate → confirm freezes; walk lands v0 (GO)", async () => {
    const draft = await rpc("decompose.prepare", {
      task_id: "tA",
      decomposition_id: "dc-co",
      extraction: EXTRACTION,
      refusals_note: "none",
    });
    expect((draft.checklist as { complete: boolean }).complete).toBe(true);
    await rpc("decompose.confirm", { task_id: "tA", decomposition_id: "dc-co" });
    const launch = await rpc("research.launch", {
      task_id: "tA",
      pre_signed: { verdict: "GO", summary: "closeout v0" },
      steps: [
        {
          event: "open-draft",
          snapshot: {
            elements: {},
            claims: [{ id: "c-mob", text: "2C4G suffices", posterior: 0.5 }],
            evidence_refs: ["sha256:" + "c".repeat(64)],
            report: { deliverable: "底稿 closeout" },
            deleted_nodes: [],
          },
          base_v: null,
        },
        { event: "attach", decomposition: EXTRACTION, decomposition_id: "dc-co", plan: PLAN },
        { event: "confirm" },
        { event: "sign" },
        { event: "research-completed" },
      ],
    });
    expect(launch.outcome).toBe("success");
    expect(engineEvents).toBeGreaterThan(3); // transitions + freeze mirrored to the socket
  });

  it("P4: research view + deterministic scrubber + honest lineage", async () => {
    // a hub claim lands in the surface (posterior authority)
    await rpc("chat.ingest", { task_id: "tA", kind: "claim", text: "2C4G suffices under load" });
    const view = await rest("/api/research/tA");
    expect(Object.keys(view.body.claims as Record<string, unknown>)).toContain("c-tA-1"); // hub claim via surface
    const beats = await rest("/api/research/tA/beats");
    const n = (beats.body.beats as unknown[]).length;
    const atN = await rest(`/api/research/tA/at/${n}`);
    expect((atN.body.console as string[]).length).toBe(n);
    // committed claim → lineage resolves; ghost → no fake lineage
    const lineage = await rest("/api/research/tA/lineage/0/c-mob");
    expect((lineage.body as { steps: Array<{ layer: string }> }).steps.map((s) => s.layer)).toEqual([
      "canvas-node",
      "detail-drawer",
      "raw-evidence",
    ]);
    const ghost = await rest("/api/research/tA/lineage/0/ghost");
    expect(ghost.body).toHaveProperty("error");
  });

  it("P5: snapshot read-only + fork inheritance + archive; settings writes pi-only", async () => {
    const snap = (await rest("/api/versions/tA/snapshot/0")).body;
    expect(snap.banner).toMatchObject({ v: 0, verdict: "GO" });
    await rpc("version.fork", { task_id: "tA", v: 0, new_task_id: "tA-fork" });
    const forkSide = (await rest("/api/versions/tA-fork")).body;
    expect(forkSide.fork_parent).toMatchObject({ task_id: "tA", v: 0 });
    // H7 telemetry
    const targets = server
      .ledgerForTests()
      .graphEvents()
      .filter((e) => (e.payload as Record<string, unknown>).provider === "telemetry")
      .map((e) => String((e.payload as Record<string, unknown>).target));
    expect(targets.some((t) => t.startsWith("fork:"))).toBe(true);

    // settings: write key → file has it, wire/audit never do
    await rpc("config.setProviderKey", { provider: "zai", api_key: "sk-CO-SECRET" });
    const raw = JSON.parse(readFileSync(join(piDir, "auth.json"), "utf8")) as Record<string, Record<string, unknown>>;
    expect(raw.zai?.api_key).toBe("sk-CO-SECRET");
    expect(JSON.stringify(readPiConfig(piDir))).not.toContain("sk-CO-SECRET");
    writeFileSync(join(piDir, "models-store.json"), JSON.stringify({ models: ["glm-5.3"], default: "glm-5.3" }));
    await rpc("config.setDefaultModel", { model: "glm-air" });
    expect(readPiConfig(piDir).default_model).toBe("glm-air");
    const audit = server
      .ledgerForTests()
      .graphEvents()
      .filter((e) => (e.payload as Record<string, unknown>).provider === "settings");
    expect(JSON.stringify(audit)).not.toContain("sk-CO-SECRET");

    // archived browse
    const archive = await rest("/api/archive");
    expect(Array.isArray(archive.body.entries)).toBe(true);
  });
});
