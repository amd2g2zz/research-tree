/** P5 version page tests (issue #637): timeline over the wire, fork
 * inheritance visible both ends, snapshot view read-only, H7 telemetry. */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";

const SOURCE = { kind: "chat-message", ref: "msg:1", quote: "q" };
const EXTRACTION = {
  requirements: [{ text: "d", source: SOURCE }],
  constraints: [{ text: "c", source: SOURCE }],
  background: [{ text: "b", source: SOURCE }],
  intents: [{ text: "i", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "m", source: SOURCE, kill_candidates: ["c-mob"] }],
  claims_preview: [],
};
const PLAN = {
  plan_id: "plan-p5",
  stages: [{ id: "s1", title: "recon", claim_ids: [], depends_on: [] }],
  budget: { capMs: 12 * 3600 * 1000 },
  yaw_checks: [
    { slot: "plan-level", mode: "auto" },
    { slot: "problem-level", mode: "human" },
    { slot: "knowledge-level", mode: "auto" },
  ],
};

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;

beforeAll(async () => {
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-p5-")),
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

async function rest(path: string): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await fetch(`http://127.0.0.1:${port}${path}`);
  return {
    status: res.status,
    body: (await res.json()) as Record<string, unknown>,
  };
}

function launch(taskId: string, verdict: string, summary: string): Promise<Record<string, unknown>> {
  return rpc("research.launch", {
    task_id: taskId,
    pre_signed: { verdict, summary },
    steps: [
      {
        event: "open-draft",
        snapshot: {
          elements: {},
          claims: [{ id: "c-mob", text: "2C4G suffices", posterior: 0.5 }],
          evidence_refs: ["sha256:" + "f".repeat(64)],
          report: { deliverable: `底稿 ${summary}` },
          deleted_nodes: [],
        },
        base_v: null,
      },
      {
        event: "attach",
        decomposition: EXTRACTION,
        decomposition_id: `dc-${taskId}-${summary}`,
        plan: PLAN,
      },
      { event: "confirm" },
      { event: "sign" },
      { event: "research-completed" },
    ],
  });
}

describe("P5 version page (issue #637)", () => {
  it("timeline newest-first with fork markers; draft row shows and vanishes on freeze", async () => {
    await rpc("project.create", { project_id: "pV", name: "版本项目" });
    await rpc("project.registerTask", {
      project_id: "pV",
      task_id: "tV",
      role: "main",
    });
    await launch("tV", "GO", "first");
    // version+1 via 继续研究: a draft opens from the latest commit
    await rpc("version.continue", { task_id: "tV" });
    let view = (await rest("/api/versions/tV")).body;
    expect(view.draft).not.toBeNull();
    // freeze consumes the draft
    await launch("tV", "PARK", "second");
    view = (await rest("/api/versions/tV")).body;
    expect(view.draft).toBeNull();
    expect((view.versions as Array<Record<string, unknown>>).map((v) => v.v)).toEqual([1, 0]);
    expect((view.versions as Array<Record<string, unknown>>).every((v) => String(v.commit_hash).length === 64)).toBe(
      true,
    );
    expect(view.is_main_branch).toBe(true);

    // fork from v0 → marker on both ends, new task in chat with inherited snapshot
    await rpc("version.fork", { task_id: "tV", v: 0, new_task_id: "tV-fork" });
    const forkView = (await rest("/api/versions/tV")).body;
    const v0 = (forkView.versions as Array<Record<string, unknown>>).find((v) => v.v === 0);
    expect(v0?.forked).toBe(true);
    const forkSide = (await rest("/api/versions/tV-fork")).body;
    expect(forkSide.is_main_branch).toBe(false);
    expect(forkSide.fork_parent).toMatchObject({ task_id: "tV", v: 0 });
    // the fork line is REGISTERED into the project (#655 e2e finding): the
    // tree shows the支线 without a manual registerTask
    const tree = (await rest("/api/tree")).body.projects as Array<Record<string, unknown>>;
    const pV = tree.find((p) => p.project_id === "pV")!;
    expect((pV.lines as Array<Record<string, unknown>>).map((l) => l.task_id)).toContain("tV-fork");
    const status = await rpc("task.status", { task_id: "tV-fork" });
    expect(status.phase).toBe("chat");

    // H7 telemetry landed for both actions
    const events = server
      .ledgerForTests()
      .graphEvents()
      .filter((e) => (e.payload as Record<string, unknown>).provider === "telemetry");
    const targets = events.map((e) => String((e.payload as Record<string, unknown>).target));
    expect(targets.some((t) => t.startsWith("fork:"))).toBe(true);
    expect(targets.some((t) => t.startsWith("version-continue"))).toBe(true);
  });

  it("snapshot view is read-only: frozen banner + report; unknown versions 404", async () => {
    const snap = (await rest("/api/versions/tV/snapshot/0")).body;
    expect(snap.banner).toMatchObject({ v: 0, verdict: "GO" });
    expect(String((snap.banner as Record<string, unknown>).commit_hash)).toHaveLength(64);
    expect((snap.report as Record<string, unknown>).deliverable).toBe("底稿 first");
    await expect(rest("/api/versions/tV/snapshot/9")).resolves.toMatchObject({
      status: 404,
    });
    await expect(rest("/api/versions/ghost")).resolves.toMatchObject({
      status: 404,
    });
  });
});
