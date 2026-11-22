/** TaskControlPlane tests (issue #742): 任务级 stop 控制面——持久化状态机
 * running→stopping→stopped 单向、幂等、重启 hydrate。
 *
 * 篡改检测式断言（engine.test.ts 模式）：绕过状态机直写 SQL 必须被
 * CHECK 约束/状态机拒绝或可检出，而不是静默接受。 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerIntegrityError } from "../src/store/integrity.js";
import { LedgerStore } from "../src/store/ledger.js";
import { TaskControlPlane } from "../src/state/task_control.js";

let ledger: LedgerStore;
let workspace: string;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-control-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

describe("task_control migration v11 (#742 控制面持久化)", () => {
  it("migration v11 创建 task_control 表（status 域受限）", () => {
    const row = ledger.connection
      .prepare("SELECT version FROM schema_migrations WHERE version = 11")
      .get() as { version: number } | undefined;
    expect(row?.version).toBe(11);
    // CHECK 约束拒绝非法状态值（绕过状态机的直写被 SQLite 拒绝）
    expect(() =>
      ledger.connection
        .prepare("INSERT INTO task_control(task_id, status, stop_reason, stop_requested_at, updated_at) VALUES(?,?,?,?,?)")
        .run("tX", "resumed", null, null, new Date().toISOString()),
    ).toThrow(/CHECK constraint failed/);
  });
});

describe("TaskControlPlane (#742 任务级 stop 状态机)", () => {
  it("无行任务视为 running（存量任务兼容）", () => {
    const plane = new TaskControlPlane(ledger);
    expect(plane.statusOf("t-legacy")).toBe("running");
    expect(plane.stateOf("t-legacy")).toBeNull();
  });

  it("requestStop：running → stopping，持久化行带 stop_requested_at 与 reason", () => {
    const plane = new TaskControlPlane(ledger);
    const state = plane.requestStop("tA", "user stop");
    expect(state.status).toBe("stopping");
    expect(state.stopReason).toBe("user stop");
    expect(state.stopRequestedAt).not.toBeNull();
    const row = ledger.connection
      .prepare("SELECT status, stop_reason FROM task_control WHERE task_id = ?")
      .get("tA") as { status: string; stop_reason: string };
    expect(row.status).toBe("stopping");
    expect(row.stop_reason).toBe("user stop");
  });

  it("重复 requestStop 幂等：状态不变、仍只有一行、stop_requested_at 不刷新", () => {
    const plane = new TaskControlPlane(ledger);
    const first = plane.requestStop("tA", "first");
    const second = plane.requestStop("tA", "second");
    expect(second.status).toBe("stopping");
    expect(second.stopRequestedAt).toBe(first.stopRequestedAt); // 幂等：时间戳不刷新
    expect(second.stopReason).toBe("first"); // 首个理由保留
    const count = ledger.connection
      .prepare("SELECT COUNT(*) AS n FROM task_control WHERE task_id = ?")
      .get("tA") as { n: number };
    expect(count.n).toBe(1);
  });

  it("markStopped：stopping → stopped（单向可达终态）", () => {
    const plane = new TaskControlPlane(ledger);
    plane.requestStop("tA");
    const state = plane.markStopped("tA");
    expect(state.status).toBe("stopped");
    expect(plane.statusOf("tA")).toBe("stopped");
  });

  it("markStopped 从 running 直接调用被拒——单向不可跳过（fail-closed）", () => {
    const plane = new TaskControlPlane(ledger);
    expect(() => plane.markStopped("tA")).toThrow(LedgerIntegrityError);
  });

  it("stopped 后 requestStop 是 no-op（返回 stopped，行不变）", () => {
    const plane = new TaskControlPlane(ledger);
    plane.requestStop("tA");
    plane.markStopped("tA");
    const again = plane.requestStop("tA", "late click");
    expect(again.status).toBe("stopped");
    expect(again.stopReason).toBeNull(); // 原状态未被污染
  });

  it("重启 hydrate：新 plane 在同一 ledger 上恢复 stopped（issue 验收：重启后保持）", () => {
    const plane = new TaskControlPlane(ledger);
    plane.requestStop("tA");
    plane.markStopped("tA");
    plane.requestStop("tB");
    // 模拟进程重启：全新 plane 实例读同一 ledger
    const rebooted = new TaskControlPlane(ledger);
    expect(rebooted.statusOf("tA")).toBe("stopped");
    expect(rebooted.statusOf("tB")).toBe("stopping");
    expect(rebooted.statusOf("tC")).toBe("running"); // 无行 = running
  });

  it("controlledTaskIds 列出全部非 running 任务（派发守卫的排除集）", () => {
    const plane = new TaskControlPlane(ledger);
    plane.requestStop("tA");
    plane.markStopped("tA");
    plane.requestStop("tB");
    const ids = plane.controlledTaskIds();
    expect(ids).toContain("tA");
    expect(ids).toContain("tB");
    expect(ids).not.toContain("tC");
  });
});
