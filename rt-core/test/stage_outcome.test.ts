import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import Database from "better-sqlite3";
import { beforeEach, describe, expect, it } from "vitest";

import {
	parseStageOutputs,
	type StageOutcome,
} from "../src/scheduler/stage_outcome.js";
import { LedgerStore, MIGRATIONS } from "../src/store/ledger.js";

let ledger: LedgerStore;

beforeEach(() => {
	ledger = new LedgerStore(mkdtempSync(join(tmpdir(), "rt-outcome-")));
	ledger.initialize();
});

/** dogfood ISSUE-004 时代的裸 artifact 行（#744 之前的 outputs 形态）：
 * 双重编码的数组包一个 artifact 对象。 */
function legacyOutputsRow(): string {
	return JSON.stringify([
		JSON.stringify({
			title: "探索｜任务背景",
			query: "任务背景",
			findings: "资料不足，不能得出真实结论",
			sources: [
				{ title: "《原神》须弥主线剧情全解析", url: "https://game.example" },
				{ title: "宇宙探索的下一个十年", url: "https://space.example" },
			],
			completed_at: "2026-11-16T10:00:00.000Z",
		}),
	]);
}

describe("StageOutcome 四态结构化（issue #744）", () => {
	it("legacy 裸 artifact 行解析为 execution=executed / sufficiency=unknown 显式标注", () => {
		const outcome = parseStageOutputs(legacyOutputsRow());
		expect(outcome.execution).toBe("executed");
		expect(outcome.sufficiency).toBe("unknown");
		expect(outcome.schema).toBe(2);
		expect(outcome.relevance).toEqual([]);
		expect(outcome.unresolvedClaims).toEqual([]);
		// 迁移不丢数据：finding 文本与来源仍可读（画布 projection 依赖）
		expect(outcome.findings[0]?.text).toContain("资料不足");
		expect(outcome.sources).toHaveLength(2);
	});

	it("legacy 原文逐字段保留在 legacy（篡改检测式：改一字必须可检出）", () => {
		const row = legacyOutputsRow();
		const outcome = parseStageOutputs(row);
		const artifact = outcome.legacy as { findings: string };
		expect(artifact.findings).toBe("资料不足，不能得出真实结论");
		const tampered = (JSON.parse(row) as string[]).map((s) =>
			s.replace("资料不足", "资料充足"),
		);
		const tamperedOutcome = parseStageOutputs(JSON.stringify(tampered));
		expect((tamperedOutcome.legacy as { findings: string }).findings).toBe(
			"资料充足，不能得出真实结论",
		);
	});

	it("StageOutcome 新形态往返：字段原样保留", () => {
		const outcome: StageOutcome = {
			schema: 2,
			execution: "executed",
			sufficiency: "insufficient",
			relevance: [
				{ sourceRef: "s1", verdict: "irrelevant", basis: "重叠 0.00" },
			],
			unresolvedClaims: ["小型医院 AI 病历摘要试点需要一份风险报告"],
			findings: [],
			sources: [{ title: "游戏源", url: "https://game.example" }],
			query: "任务背景",
			stopReason: "all-sources-irrelevant",
		};
		const round = parseStageOutputs(JSON.stringify(outcome));
		expect(round).toEqual(outcome);
	});

	it("损坏 outputs fail-closed：不崩溃、sufficiency=unknown、解析失败显式标注", () => {
		const outcome = parseStageOutputs("not-json-at-all");
		expect(outcome.execution).toBe("executed");
		expect(outcome.sufficiency).toBe("unknown");
		expect(outcome.unresolvedClaims.length).toBeGreaterThan(0);
		expect(outcome.unresolvedClaims[0]).toContain("解析失败");
	});

	it("空数组/空对象等边缘形态同样 fail-closed 到 unknown", () => {
		expect(parseStageOutputs("[]").sufficiency).toBe("unknown");
		expect(parseStageOutputs("{}").sufficiency).toBe("unknown");
	});
});

describe("ledger migration v12（outputs 裸 JSON → StageOutcome，不丢数据）", () => {
	function legacyDb(): Database.Database {
		const db = new Database(join(tmpdir(), `rt-mig-${Date.now()}-${Math.random()}`));
		// 只回放 v1..v10——复现 v12 之前的真实库状态
		for (const m of MIGRATIONS.filter((x) => x.version <= 10)) {
			if (m.statements !== undefined) db.exec(m.statements);
		}
		db.prepare(
			"INSERT INTO parallel_stages(stage_id, title, status, claim_ids, depends_on, " +
				"assigned_worker_class, retries, max_retries, outputs) VALUES(?,?,?,?,?,?,?,?,?)",
		).run("t1/s1", "探索｜任务背景", "complete", "[]", "[]", "retrieval", 0, 2, legacyOutputsRow());
		// 一行已是新形态（模拟部分升级）——迁移必须跳过它
		const fresh: StageOutcome = {
			schema: 2,
			execution: "executed",
			sufficiency: "sufficient",
			relevance: [],
			unresolvedClaims: [],
			findings: [],
			sources: [],
		};
		db.prepare(
			"INSERT INTO parallel_stages(stage_id, title, status, claim_ids, depends_on, " +
				"assigned_worker_class, retries, max_retries, outputs) VALUES(?,?,?,?,?,?,?,?,?)",
		).run("t1/s2", "探索｜调研目标", "complete", "[]", "[]", "retrieval", 0, 2, JSON.stringify(fresh));
		return db;
	}

	function outputsOf(db: Database.Database, stageId: string): string {
		const row = db.prepare("SELECT outputs FROM parallel_stages WHERE stage_id = ?").get(stageId) as {
			outputs: string;
		} | undefined;
		return row?.outputs ?? "";
	}

	it("v12 重写旧行：显式标注 + legacy 保留原 artifact + 新行跳过", () => {
		const db = legacyDb();
		const v12 = MIGRATIONS.find((m) => m.version === 12);
		expect(v12).toBeDefined();
		expect(typeof v12!.run).toBe("function");
		v12!.run!(db);
		const migrated = parseStageOutputs(outputsOf(db, "t1/s1"));
		expect(migrated.execution).toBe("executed");
		expect(migrated.sufficiency).toBe("unknown");
		expect(migrated.findings[0]?.text).toContain("资料不足");
		expect(migrated.sources).toHaveLength(2);
		const legacy = migrated.legacy as { completed_at: string };
		expect(legacy.completed_at).toBe("2026-11-16T10:00:00.000Z");
		// 已是新形态的行原样跳过（幂等）
		const untouched = parseStageOutputs(outputsOf(db, "t1/s2"));
		expect(untouched.sufficiency).toBe("sufficient");
		expect(untouched.legacy).toBeUndefined();
	});

	it("v12 幂等：重复执行不二次包装", () => {
		const db = legacyDb();
		const v12 = MIGRATIONS.find((m) => m.version === 12)!;
		v12.run!(db);
		const once = outputsOf(db, "t1/s1");
		v12.run!(db);
		expect(outputsOf(db, "t1/s1")).toBe(once);
	});
});
