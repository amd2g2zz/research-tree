/** TaskControlPlane tests (#742)：持久化状态机单向/幂等/hydrate。篡改检测式
 * 断言（engine.test.ts 模式）：绕过状态机直写 SQL 被 CHECK 约束/状态机拒绝。 */

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

  it("requestStop：running → stopping 持久化；重复调用幂等（单行、时间戳不刷新）", () => {
    const plane = new TaskControlPlane(ledger);
    const first = plane.requestStop("tA", "first");
    expect(first.status).toBe("stopping");
    expect(first.stopRequestedAt).not.toBeNull();
    const row = ledger.connection
      .prepare("SELECT status, stop_reason FROM task_control WHERE task_id = ?")
      .get("tA") as { status: string; stop_reason: string };
    expect(row.status).toBe("stopping");
    expect(row.stop_reason).toBe("first");
    // 幂等：状态不变、时间戳不刷新、首个理由保留、仍只有一行
    const second = plane.requestStop("tA", "second");
    expect(second).toEqual(first);
    const count = ledger.connection
      .prepare("SELECT COUNT(*) AS n FROM task_control WHERE task_id = ?")
      .get("tA") as { n: number };
    expect(count.n).toBe(1);
  });

  it("markStopped：running 直调 fail-closed 拒；stopping → stopped 终态；stopped 后 requestStop no-op", () => {
    const plane = new TaskControlPlane(ledger);
    expect(() => plane.markStopped("tA")).toThrow(LedgerIntegrityError); // 单向不可跳过
    plane.requestStop("tA");
    expect(plane.markStopped("tA").status).toBe("stopped");
    expect(plane.statusOf("tA")).toBe("stopped");
    const again = plane.requestStop("tA", "late click"); // 终态后请求是 no-op
    expect(again.status).toBe("stopped");
    expect(again.stopReason).toBeNull(); // 原状态未被污染
  });

  it("重启 hydrate + controlledTaskIds：新 plane 同一 ledger 恢复两态；排除集列全部非 running", () => {
    const plane = new TaskControlPlane(ledger);
    plane.requestStop("tA");
    plane.markStopped("tA");
    plane.requestStop("tB");
    // 模拟进程重启：全新 plane 实例读同一 ledger（issue 验收：重启后保持）
    const rebooted = new TaskControlPlane(ledger);
    expect(rebooted.statusOf("tA")).toBe("stopped");
    expect(rebooted.statusOf("tB")).toBe("stopping");
    expect(rebooted.statusOf("tC")).toBe("running"); // 无行 = running
    const ids = rebooted.controlledTaskIds(); // 派发守卫的排除集
    expect(ids).toContain("tA");
    expect(ids).toContain("tB");
    expect(ids).not.toContain("tC");
  });
});
