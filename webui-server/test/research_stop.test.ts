/** research.stop over-the-wire（#742）：WS 过线证明——全链路 stop→排干落
 * stopped + 幂等 + 冷进程重启 hydrate + start 拒绝。runner 层完整矩阵见
 * task_stop.test.ts，此处只证 RPC/服务器接线。 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { createBlockedProvider, until } from "./fixtures/blocked_provider.js";
import { WebUIServer } from "../src/server.js";

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

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let nextId = 1;
let blocked: ReturnType<typeof createBlockedProvider>;

function workspaceFor(s: WebUIServer): string {
  return (s as unknown as { options: { workspace: string } }).options.workspace;
}

function rpcOn(socket: WebSocket, method: string, params: Record<string, unknown> = {}, id?: number) {
  const msgId = id ?? nextId++;
  return new Promise<Record<string, unknown>>((resolve, reject) => {
    const onMessage = (data: unknown): void => {
      const msg = JSON.parse(String(data)) as Record<string, unknown>;
      if (msg.id === msgId) {
        socket.off("message", onMessage);
        if (msg.ok === true) resolve(msg.result as Record<string, unknown>);
        else reject(new Error(String(msg.error)));
      }
    };
    socket.on("message", onMessage);
    socket.send(JSON.stringify({ id: msgId, method, params }));
  });
}

const rpc = (method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> =>
  rpcOn(ws, method, params);

async function restJson(path: string): Promise<Record<string, unknown>> {
  return (await (await fetch(`http://127.0.0.1:${port}${path}`)).json()) as Record<string, unknown>;
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
  it("stop 全链路：stopping 持久化→阶段取消→不可取消如实上报→幂等→排干落 stopped", async () => {
    await setupResearchTask("tStop");
    const stop = await rpc("research.stop", { task_id: "tStop", reason: "user stop" });
    expect((stop.control as Record<string, unknown>).status).toBe("stopping");
    expect((stop.control as Record<string, unknown>).stop_reason).toBe("user stop");

    const view = await restJson("/api/research/tStop");
    expect((view.stages as Array<{ status: string }>)[0]!.status).toBe("cancelled");
    expect(((view.control as Record<string, unknown> | null) ?? {}).status).toBe("stopping");
    // 重复 stop 幂等：状态与时间戳不刷新
    const again = await rpc("research.stop", { task_id: "tStop", reason: "double click" });
    expect((again.control as Record<string, unknown>).stop_requested_at).toBe(
      (stop.control as Record<string, unknown>).stop_requested_at,
    );

    blocked.release(); // 迟到检索结果 → 排干 → stopped
    await until(async () =>
      ((await rpc("task.status", { task_id: "tStop" })).control as Record<string, unknown> | null)?.status ===
        "stopped",
    );
    const control = (await rpc("task.status", { task_id: "tStop" })).control as Record<string, unknown>;
    expect(control.status).toBe("stopped");
    expect(control.stop_requested_at).not.toBeNull();
  });

  it("冷进程重启 hydrate：fresh server 恢复 stopped、拒绝 research.start 复燃", async () => {
    await setupResearchTask("tDur");
    await rpc("research.stop", { task_id: "tDur" });
    blocked.release();
    await until(async () =>
      ((await rpc("task.status", { task_id: "tDur" })).control as Record<string, unknown> | null)?.status ===
        "stopped",
    );

    // 冷进程：全新 WebUIServer 读同一 workspace
    const fresh = new WebUIServer({
      workspace: workspaceFor(server),
      piConfigDir: mkdtempSync(join(tmpdir(), "rt-stop-fresh-")),
    });
    const freshPort = await fresh.listen();
    try {
      const socket = await new Promise<WebSocket>((resolve, reject) => {
        const s = new WebSocket(`ws://127.0.0.1:${freshPort}/ws`);
        s.on("open", () => resolve(s));
        s.on("error", reject);
      });
      const status = await rpcOn(socket, "task.status", { task_id: "tDur" }, 1);
      expect(((status.control as Record<string, unknown> | null) ?? {}).status).toBe("stopped"); // hydrate
      await expect(rpcOn(socket, "research.start", { task_id: "tDur", decomposition_id: "dc-tDur" }, 2)).rejects.toThrow(
        /stopped|stopping/,
      );
      socket.close();
    } finally {
      await fresh.close();
    }
  });
});
