/** Background research worker tests (issue #709): 多任务后台执行、真实检索
 * → 综合 → 阶段完成/重试、crash 恢复、前端离开不影响进度。
 * runner 的 provider / piRunner 均注入 fake——测试不依赖网络与 pi。 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";
import { ParallelDagScheduler } from "../../rt-core/src/scheduler/parallel_dag.js";
import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import { VersionStore } from "../../rt-core/src/versions/store.js";
import {
	BackgroundResearchRunner,
	type WorkerDeps,
} from "../src/research_worker.js";

let ledger: LedgerStore;
let versions: VersionStore;
let lines: string[];
let fakeProvider: DataSourceProvider & { failNext: boolean };
let piCalls: string[];
let piShouldFail: boolean;

function stageStatus(stageId: string): string {
	const row = ledger.connection
		.prepare("SELECT status FROM parallel_stages WHERE stage_id = ?")
		.get(stageId) as { status: string } | undefined;
	return row?.status ?? "unknown";
}

function stageOutputs(stageId: string): string {
	const row = ledger.connection
		.prepare("SELECT outputs FROM parallel_stages WHERE stage_id = ?")
		.get(stageId) as { outputs: string } | undefined;
	return row?.outputs ?? "[]";
}

function makeDeps(overrides: Partial<WorkerDeps> = {}): WorkerDeps {
	return {
		ledger,
		versions,
		provider: () => fakeProvider,
		piCommand: () => process.execPath,
		piRunner: (command, prompt) => {
			piCalls.push(prompt);
			if (piShouldFail) return Promise.reject(new Error("pi down"));
			return Promise.resolve(
				JSON.stringify({ findings: `综合发现（基于检索结果，命题：${queryOf(prompt)}）` }),
			);
		},
		broadcast: (line) => lines.push(line),
		maxConcurrent: 3,
		...overrides,
	};
}

function queryOf(prompt: string): string {
	const m = /检索词：(.+)$/m.exec(prompt);
	return m !== null ? m[1]!.slice(0, 12) : "?";
}

/** 注册一个任务的两个阶段（B 依赖 A），任务前缀即 task_id。 */
function registerTaskStages(taskId: string): void {
	const sched = new ParallelDagScheduler(ledger);
	sched.registerStages([
		{
			stage_id: `${taskId}/s1`,
			title: "verify: 竞品价格监控工具的付费意愿",
			status: "pending",
			claim_ids: ["c1"],
			depends_on: [],
			assigned_worker_class: "retrieval",
			retries: 0,
			max_retries: 2,
			outputs: [],
		},
		{
			stage_id: `${taskId}/s2`,
			title: "verify: 每周自动汇总三个竞品价格变化",
			status: "pending",
			claim_ids: ["c2"],
			depends_on: [`${taskId}/s1`],
			assigned_worker_class: "retrieval",
			retries: 0,
			max_retries: 2,
			outputs: [],
		},
	]);
	// 草稿 claims：claim_id → 命题文本（worker 的检索/综合输入）
	versions.openDraft(taskId, {
		snapshot: {
			elements: {},
			claims: [
				{ id: "c1", text: "竞品价格监控工具的付费意愿", posterior: 0.5 },
				{ id: "c2", text: "每周自动汇总三个竞品价格变化", posterior: 0.5 },
			],
			evidence_refs: [],
			report: {},
			deleted_nodes: [],
		},
		baseV: null,
	});
}

beforeEach(() => {
	const workspace = mkdtempSync(join(tmpdir(), "rt-worker-"));
	ledger = new LedgerStore(workspace);
	ledger.initialize();
	versions = new VersionStore(ledger);
	lines = [];
	piCalls = [];
	piShouldFail = false;
	const providerObj = {
		failNext: false,
		async search({ query }: { query: string }) {
			if (this.failNext) throw new Error("anysearch down");
			return [
				{ title: `来源A：${query}`, url: "https://a.example", snippet: "摘要A" },
				{ title: "来源B", snippet: "摘要B" },
			];
		},
	};
	fakeProvider = providerObj as DataSourceProvider & { failNext: boolean };
});

describe("BackgroundResearchRunner (#709 多任务后台调研执行)", () => {
	it("pumpOnce：真实检索 → 综合 → completeStage，产出与事件行落账", async () => {
		registerTaskStages("tA");
		const runner = new BackgroundResearchRunner(makeDeps());
		await runner.pumpOnce(); // s1 dispatch + execute
		await runner.waitForIdle();
		expect(stageStatus("tA/s1")).toBe("complete");
		const raw = JSON.parse(stageOutputs("tA/s1")) as string[];
		const artifact = JSON.parse(raw[0] ?? "{}") as {
			findings: string;
			sources: Array<{ title: string }>;
		};
		expect(artifact.findings).toContain("综合发现");
		expect(artifact.sources).toHaveLength(2);
		expect(lines.some((l) => l.includes("[worker]") && l.includes("完成"))).toBe(true);
	});

	it("依赖链：s1 完成后 s2 自动就绪并在下一次 pump 执行", async () => {
		registerTaskStages("tB");
		const runner = new BackgroundResearchRunner(makeDeps());
		await runner.pumpOnce();
		await runner.waitForIdle();
		expect(stageStatus("tB/s1")).toBe("complete");
		expect(stageStatus("tB/s2")).toBe("pending"); // 等待依赖
		await runner.pumpOnce();
		await runner.waitForIdle();
		expect(stageStatus("tB/s2")).toBe("complete");
	});

	it("检索失败 → failStage 重试计数；下次 pump 重派；成功后完成", async () => {
		registerTaskStages("tC");
		fakeProvider.failNext = true;
		const runner = new BackgroundResearchRunner(makeDeps());
		await runner.pumpOnce();
		await runner.waitForIdle();
		expect(stageStatus("tC/s1")).toBe("pending"); // 重试回位
		const row = ledger.connection
			.prepare("SELECT retries FROM parallel_stages WHERE stage_id = 'tC/s1'")
			.get() as { retries: number };
		expect(row.retries).toBe(1);
		fakeProvider.failNext = false;
		await runner.pumpOnce();
		await runner.waitForIdle();
		expect(stageStatus("tC/s1")).toBe("complete");
	});

	it("综合调用失败 → 诚实降级：检索结果作为产出，阶段仍完成", async () => {
		registerTaskStages("tD");
		piShouldFail = true;
		const runner = new BackgroundResearchRunner(makeDeps());
		await runner.pumpOnce();
		await runner.waitForIdle();
		expect(stageStatus("tD/s1")).toBe("complete");
		expect(stageOutputs("tD/s1")).toContain("来源A");
	});

	it("多任务并发：两个任务在同一 pump 各自推进", async () => {
		registerTaskStages("tX");
		registerTaskStages("tY");
		const runner = new BackgroundResearchRunner(makeDeps());
		await runner.pumpOnce();
		await runner.waitForIdle();
		expect(stageStatus("tX/s1")).toBe("complete");
		expect(stageStatus("tY/s1")).toBe("complete");
	});

	it("crash 恢复：in_progress 孤儿阶段被 failStage 重排后自动重跑", async () => {
		registerTaskStages("tZ");
		// 模拟重启残留：阶段卡在 in_progress 且无 in-flight worker
		ledger.connection
			.prepare("UPDATE parallel_stages SET status = 'in_progress' WHERE stage_id = 'tZ/s1'")
			.run();
		const runner = new BackgroundResearchRunner(makeDeps());
		await runner.pumpOnce(); // 同一泵内：孤儿重排 → 重派 → 执行完成
		await runner.waitForIdle();
		expect(stageStatus("tZ/s1")).toBe("complete");
	});
});
