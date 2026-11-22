/** 任务级 stop TDD 矩阵（issue #742）：runner 层六场景——各相位 stop、
 * 重启保持、他任务不受扰、幂等、不复燃。fixture：WS-F 可编程 fake pi +
 * 可阻塞 provider（mkdtemp + DI，行为断言非 stub 断言）。 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ParallelDagScheduler, type ParallelStage } from "../../rt-core/src/scheduler/parallel_dag.js";
import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";
import { TaskControlPlane } from "../../rt-core/src/state/task_control.js";
import { VersionStore } from "../../rt-core/src/versions/store.js";
import { createBlockedProvider, createInstantProvider, until, type BlockedProvider } from "./fixtures/blocked_provider.js";
import { createFakePiRunner, type FakePiRunner } from "./fixtures/fake_pi_runner.js";
import { BackgroundResearchRunner, type WorkerDeps } from "../src/research_worker.js";

let ledger: LedgerStore;
let versions: VersionStore;
let lines: string[];

function stageStatus(stageId: string): string {
  const row = ledger.connection.prepare("SELECT status FROM parallel_stages WHERE stage_id = ?").get(stageId) as
    | { status: string }
    | undefined;
  return row?.status ?? "unknown";
}

/** 注册一个任务的阶段（可带依赖），任务前缀即 task_id。 */
function registerStages(taskId: string, stages: Array<Partial<ParallelStage> & { id: string }>): void {
  new ParallelDagScheduler(ledger).registerStages(
    stages.map((s) => ({
      stage_id: `${taskId}/${s.id}`,
      title: s.title ?? `verify: ${taskId} 的命题 ${s.id}`,
      status: "pending" as const,
      claim_ids: [],
      depends_on: s.depends_on ?? [],
      assigned_worker_class: "retrieval" as const,
      retries: 0,
      max_retries: 2,
      outputs: [],
    })),
  );
  versions.openDraft(taskId, {
    snapshot: { elements: {}, claims: [{ id: `c-${taskId}`, text: `${taskId} 的命题`, posterior: 0.5 }], evidence_refs: [], report: {}, deleted_nodes: [] },
    baseV: null,
  });
}

interface StopHarness {
  runner: BackgroundResearchRunner;
  control: TaskControlPlane;
  blocked: BlockedProvider;
  instant: DataSourceProvider;
  fake: FakePiRunner;
}

/** 组装：provider 按查询词路由（含「甲」走阻塞，否则即时），pi 走可编程脚本。 */
function makeHarness(piScript?: Parameters<typeof createFakePiRunner>[0]): StopHarness {
  const blocked = createBlockedProvider([{ title: "阻塞来源", snippet: "阻塞摘要" }]);
  const instant = createInstantProvider([{ title: "即时来源", snippet: "即时摘要" }]);
  const provider = {
    async search(args: { query: string }) {
      if (args.query.includes("甲")) return blocked.search(args);
      return instant.search(args);
    },
  } as unknown as DataSourceProvider;
  const fake = createFakePiRunner(piScript ?? []);
  const control = new TaskControlPlane(ledger);
  const runner = new BackgroundResearchRunner({
    ledger,
    versions,
    provider: () => provider,
    piCommand: () => process.execPath,
    piRunner: fake.runner,
    broadcast: (line) => lines.push(line),
    maxConcurrent: 3,
    control,
  });
  return { runner, control, blocked, instant, fake };
}

beforeEach(() => {
  const workspace = mkdtempSync(join(tmpdir(), "rt-taskstop-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  lines = [];
});

describe("任务级 stop TDD 矩阵（#742）", () => {
  it("stop 于检索中：不可取消调用如实上报，迟到完成被拒，排干后落 stopped", async () => {
    registerStages("tA", [{ id: "s1", title: "verify: 阻塞命题甲" }]);
    const { runner, control, blocked } = makeHarness();
    const pump = runner.pumpOnce();
    await until(() => blocked.pendingSearches() === 1); // 检索在飞
    control.requestStop("tA", "user");
    runner.handleStop("tA");
    // 如实上报：检索不可取消、结果将被丢弃；阶段已取消
    expect(lines.some((l) => l.includes("不可取消"))).toBe(true);
    expect(stageStatus("tA/s1")).toBe("cancelled");
    expect(control.statusOf("tA")).toBe("stopping"); // 排干前保持 stopping

    blocked.release(); // 迟到的检索结果返回
    await pump;
    expect(control.statusOf("tA")).toBe("stopped");
    // 迟到完成被拒：无综合调用、无产出落账
    expect(stageStatus("tA/s1")).toBe("cancelled");
    const row = ledger.connection.prepare("SELECT outputs FROM parallel_stages WHERE stage_id = 'tA/s1'").get() as { outputs: string };
    expect(row.outputs).toBe("[]"); // 迟到完成被拒：无产出落账
    expect(lines.some((l) => l.includes("丢弃"))).toBe(true);
  });

  it("stop 于综合中：可取消 pi 调用被取消，阶段取消不落产出", async () => {
    registerStages("tB", [{ id: "s1", title: "verify: 即时命题乙" }]);
    const { runner, control, fake } = makeHarness([{ block: true }]);
    const pump = runner.pumpOnce();
    await until(() => fake.calls.length === 1); // 综合调用在飞

    control.requestStop("tB", "user");
    runner.handleStop("tB"); // 取消句柄触发（fake 的阻塞 promise 不会 resolve）
    await pump;
    expect(control.statusOf("tB")).toBe("stopped");
    expect(stageStatus("tB/s1")).toBe("cancelled");
    const row = ledger.connection.prepare("SELECT outputs FROM parallel_stages WHERE stage_id = 'tB/s1'").get() as { outputs: string };
    expect(row.outputs).toBe("[]"); // 综合未落账
  });

  it("stop 于仲裁中：仲裁调用被取消，图不生长，诚实闭合", async () => {
    // 依赖缺失的 stage 永不可派发 → nextWave 空 → 仲裁员决定生长
    registerStages("tC", [{ id: "s1", title: "verify: 缺依赖命题丙", depends_on: ["tC/missing"] }]);
    const { runner, control, fake } = makeHarness([{ block: true }]);
    const pump = runner.pumpOnce();
    await until(() => fake.calls.length === 1); // 仲裁调用在飞

    control.requestStop("tC", "user");
    runner.handleStop("tC"); // 取消仲裁调用
    await pump;
    expect(control.statusOf("tC")).toBe("stopped");
    const cnt = ledger.connection.prepare("SELECT COUNT(*) AS n FROM parallel_stages WHERE stage_id LIKE 'tC/%'").get() as { n: number };
    expect(cnt.n).toBe(1); // 图未生长（无新节点）
    expect(stageStatus("tC/s1")).toBe("cancelled");
    expect(lines.some((l) => l.includes("仲裁员不可用"))).toBe(true);
  });
  it("并发他任务不受扰：tA 停止期间 tB 正常派发、完成、闭合", async () => {
    registerStages("tA", [{ id: "s1", title: "verify: 阻塞命题甲" }]);
    registerStages("tB", [{ id: "s1", title: "verify: 即时命题乙" }]);
    const { runner, control, blocked } = makeHarness();
    const pump = runner.pumpOnce();
    await until(() => {
      const row = ledger.connection
        .prepare("SELECT status FROM parallel_stages WHERE stage_id = 'tB/s1'")
        .get() as { status: string } | undefined;
      return row?.status === "complete";
    }); // tB 已完成

    control.requestStop("tA", "user");
    runner.handleStop("tA");
    blocked.release();
    await pump;
    // 其它任务不受扰：tB 完成且其图闭合（注册汇总）
    expect(stageStatus("tB/s1")).toBe("complete");
    const summary = ledger.connection
      .prepare("SELECT stage_id FROM parallel_stages WHERE stage_id LIKE 'tB/%' AND title LIKE '汇总%'")
      .get() as { stage_id: string } | undefined;
    expect(summary?.stage_id).toBeDefined();
    // tA 停止
    expect(control.statusOf("tA")).toBe("stopped");
    expect(stageStatus("tA/s1")).toBe("cancelled");
    // tB 控制状态仍是 running（无行）
    expect(control.statusOf("tB")).toBe("running");
  });

  it("重复 stop 幂等：stopping 保持、行数/广播不重复；排干后 stopped（再 stop 是 no-op）", async () => {
    registerStages("tD", [{ id: "s1", title: "verify: 阻塞命题甲" }]);
    const { runner, control, blocked } = makeHarness();
    const pump = runner.pumpOnce();
    await until(() => blocked.pendingSearches() === 1); // 检索在飞——排干前保持 stopping

    const first = control.requestStop("tD", "first");
    runner.handleStop("tD");
    expect(control.statusOf("tD")).toBe("stopping");
    const linesAfterFirst = [...lines];
    const second = control.requestStop("tD", "second");
    runner.handleStop("tD");
    expect(second).toEqual(first); // 幂等：状态不变、时间戳不刷新、首个理由保留
    expect(lines).toEqual(linesAfterFirst); // 广播不重复
    const count = ledger.connection.prepare("SELECT COUNT(*) AS n FROM task_control WHERE task_id = ?").get("tD") as { n: number };
    expect(count.n).toBe(1);

    blocked.release();
    await pump;
    expect(control.statusOf("tD")).toBe("stopped"); // 排干后 stopped
    // stopped 后再 stop：幂等 no-op（状态不变、广播不重复）
    const linesAfterStopped = [...lines];
    expect(control.requestStop("tD", "late").status).toBe("stopped");
    runner.handleStop("tD");
    expect(lines).toEqual(linesAfterStopped);
  });

  it("重启后 stopped 保持：新 runner/plane 在同一 ledger 上不派发、不复活", async () => {
    registerStages("tE", [{ id: "s1", title: "verify: 即时命题戊" }]);
    const first = makeHarness();
    first.control.requestStop("tE", "user");
    first.runner.handleStop("tE");
    expect(first.control.statusOf("tE")).toBe("stopped");

    // 模拟重启：全新 runner + 全新 control plane，同一 ledger
    const rebooted = makeHarness();
    expect(rebooted.control.statusOf("tE")).toBe("stopped"); // hydrate 恢复
    await rebooted.runner.pumpOnce();
    expect(stageStatus("tE/s1")).toBe("cancelled"); // 未复活
    expect(rebooted.fake.calls).toHaveLength(0); // 零 pi 调用

    // 模式切换/重新注册也不复燃：新 stage 注册后 pump 不派发
    registerStages("tE", [{ id: "s2", title: "verify: 新命题戊" }]);
    await rebooted.runner.pumpOnce();
    expect(stageStatus("tE/s2")).toBe("pending"); // 停止任务零派发
    expect(rebooted.control.statusOf("tE")).toBe("stopped");
  });
});
