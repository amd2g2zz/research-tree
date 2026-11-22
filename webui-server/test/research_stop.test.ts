/** research.stop RPC over-the-wire tests（issue #742）：真实 WS 流量——
 * stop 状态持久化、重复 stop 幂等、stopped 后 research.start 拒绝（模式
 * 切换不复燃）、重启 hydrate 后保持。fake blocked provider 确定性驱动
 * （检索在飞 → stop → 迟到结果丢弃 → 排干落 stopped）。 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import { createBlockedProvider } from "./fixtures/blocked_provider.js";
import { WebUIServer } from "../src/server.js";

const SOURCE = {
  kind: "chat-message" as const,
  ref: "msg:1",
  quote: "2C4G 越快上越好",
};
const EXTRACTION = {
  requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
  constraints: [{ text: "2C4G is a guess", source: SOURCE, hardness: "guessed" }],
  background: [{ text: "pilot feedback", source: SOURCE }],
  intents: [{ text: "ship fast", source: SOURCE }],
  refusals: [],
  difficulties: [{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] }],
  claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
};

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;
let blocked: ReturnType<typeof createBlockedProvider>;

function workspaceFor(s: WebUIServer): string {
  return (s as unknown as { options: { workspace: string } }).options.workspace;
}

async function until(cond: () => boolean | Promise<boolean>, timeoutMs = 5000): Promise<void> {
  const start = Date.now();
  while (!(await cond())) {
    if (Date.now() - start > timeoutMs) throw new Error("condition not met within timeout");
    await new Promise((r) => setTimeout(r, 20));
  }
}

async function restJson(path: string): Promise<Record<string, unknown>> {
  const res = await fetch(`http://127.0.0.1:${port}${path}`);
  return (await res.json()) as Record<string, unknown>;
}

beforeAll(async () => {
  blocked = createBlockedProvider([{ title: "阻塞来源", snippet: "阻塞摘要" }]);
  server = new WebUIServer({
    workspace: mkdtempSync(join(tmpdir(), "rt-stop-")),
    piConfigDir: mkdtempSync(join(tmpdir(), "rt-stop-pi-")),
    provider: blocked as never,
    runnerIntervalMs: 50, // 确定性测试：泵 50ms 一轮（生产默认 5000）
  });
  port = await server.listen();
  ws = await new Promise<WebSocket>((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    socket.on("open", () => resolve(socket));
    socket.on("error", reject);
  });
});

afterAll(async () => {
  await server.close();
  ws?.close();
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

async function setupResearchTask(taskId: string): Promise<void> {
  await rpc("project.create", { project_id: `p-${taskId}`, name: "stop 项目" });
  await rpc("project.registerTask", { project_id: `p-${taskId}`, task_id: taskId, role: "main" });
  await rpc("decompose.prepare", {
    task_id: taskId,
    decomposition_id: `dc-${taskId}`,
    extraction: EXTRACTION,
    refusals_note: "none",
  });
  await rpc("decompose.confirm", { task_id: taskId, decomposition_id: `dc-${taskId}` });
  const start = await rpc("research.start", { task_id: taskId, decomposition_id: `dc-${taskId}` });
  expect(Number(start.stages)).toBe(1);
  await until(() => blocked.pendingSearches() === 1); // 后台泵已派发并阻塞在检索
}

describe("research.stop 任务级停止（#742 over the wire）", () => {
  it("stop：stopping 持久化、阶段取消、不可取消如实上报、排干落 stopped", async () => {
    await setupResearchTask("tStop");
    const stop = await rpc("research.stop", { task_id: "tStop", reason: "user stop" });
    expect((stop.control as Record<string, unknown>).status).toBe("stopping");
    expect((stop.control as Record<string, unknown>).stop_reason).toBe("user stop");

    // 阶段取消（画布可见的终态）
    const view = await restJson("/api/research/tStop");
    const stages = view.stages as Array<{ status: string }>;
    expect(stages).toHaveLength(1);
    expect(stages[0]!.status).toBe("cancelled");
    // task.status / researchView 携带 control
    const viewControl = view.control as Record<string, unknown> | null;
    expect(viewControl?.status).toBe("stopping");

    // 迟到检索结果返回 → 排干 → stopped
    blocked.release();
    await until(async () => {
      const status = await rpc("task.status", { task_id: "tStop" });
      return ((status.control as Record<string, unknown> | null)?.status) === "stopped";
    });
    const status = await rpc("task.status", { task_id: "tStop" });
    const control = status.control as Record<string, unknown>;
    expect(control.status).toBe("stopped");
    expect(control.stop_requested_at).not.toBeNull();
  });

  it("重复 stop 幂等：状态不变，阶段不重复翻转", async () => {
    await setupResearchTask("tAgain");
    const first = await rpc("research.stop", { task_id: "tAgain" });
    const second = await rpc("research.stop", { task_id: "tAgain", reason: "double click" });
    expect((second.control as Record<string, unknown>).status).toBe(
      (first.control as Record<string, unknown>).status,
    );
    expect((second.control as Record<string, unknown>).stop_requested_at).toBe(
      (first.control as Record<string, unknown>).stop_requested_at, // 时间戳不刷新
    );
    blocked.release(); // 排干
    await until(async () => {
      const status = await rpc("task.status", { task_id: "tAgain" });
      return ((status.control as Record<string, unknown> | null)?.status) === "stopped";
    });
  });

  it("stopped 后 research.start 拒绝——模式切换不复燃", async () => {
    await setupResearchTask("tNoResume");
    await rpc("research.stop", { task_id: "tNoResume" });
    blocked.release();
    await until(async () => {
      const status = await rpc("task.status", { task_id: "tNoResume" });
      return ((status.control as Record<string, unknown> | null)?.status) === "stopped";
    });
    await expect(rpc("research.start", { task_id: "tNoResume", decomposition_id: "dc-tNoResume" })).rejects.toThrow(
      /stopped|stopping/,
    );
    // 阶段未被复活/新增
    const ledger = new LedgerStore(join(workspaceFor(server), "ledger.sqlite"));
    const stages = ledger.connection
      .prepare("SELECT status FROM parallel_stages WHERE stage_id LIKE 'tNoResume/%'")
      .all() as Array<{ status: string }>;
    expect(stages.every((s) => s.status === "cancelled")).toBe(true);
  });

  it("重启 hydrate：fresh server 从 ledger 恢复 stopped 并拒绝重启研究", async () => {
    await setupResearchTask("tDur");
    await rpc("research.stop", { task_id: "tDur" });
    blocked.release();
    await until(async () => {
      const status = await rpc("task.status", { task_id: "tDur" });
      return ((status.control as Record<string, unknown> | null)?.status) === "stopped";
    });

    // 冷进程：全新 WebUIServer 读同一 workspace
    const fresh = new WebUIServer({ workspace: workspaceFor(server), piConfigDir: mkdtempSync(join(tmpdir(), "rt-stop-fresh-")) });
    const freshPort = await fresh.listen();
    try {
      const socket = await new Promise<WebSocket>((resolve, reject) => {
        const s = new WebSocket(`ws://127.0.0.1:${freshPort}/ws`);
        s.on("open", () => resolve(s));
        s.on("error", reject);
      });
      const status = await new Promise<Record<string, unknown>>((resolve, reject) => {
        const onMessage = (data: unknown): void => {
          const msg = JSON.parse(String(data)) as Record<string, unknown>;
          if (msg.id === 1) {
            socket.off("message", onMessage);
            if (msg.ok === true) resolve(msg.result as Record<string, unknown>);
            else reject(new Error(String(msg.error)));
          }
        };
        socket.on("message", onMessage);
        socket.send(JSON.stringify({ id: 1, method: "task.status", params: { task_id: "tDur" } }));
      });
      const control = status.control as Record<string, unknown> | null;
      expect(control?.status).toBe("stopped"); // 重启后保持（issue 验收原文）
      socket.close();
    } finally {
      await fresh.close();
    }
  });
});
