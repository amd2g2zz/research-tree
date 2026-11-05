/** P4 research page tests (issue #636): three-layer view + #572 scrubber
 * wired over the wire — live state, beats, projection(t) determinism in the
 * browser's traffic, and lineage clicks. */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import {
	ParallelDagScheduler,
	type ParallelStage,
} from "../../rt-core/src/scheduler/parallel_dag.js";
import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import { WebUIServer } from "../src/server.js";

const SOURCE = { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" };
const EXTRACTION = {
	requirements: [{ text: "deploy fast", source: SOURCE }],
	constraints: [{ text: "2C4G guess", source: SOURCE, hardness: "guessed" }],
	background: [{ text: "b", source: SOURCE }],
	intents: [{ text: "i", source: SOURCE }],
	refusals: [],
	difficulties: [
		{ text: "memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] },
	],
	claims_preview: [
		{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM" },
	],
};
const PLAN = {
	plan_id: "plan-p4",
	stages: [{ id: "s1", title: "recon", claim_ids: ["c-mob"], depends_on: [] }],
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

function workspaceFor(s: WebUIServer): string {
	return (s as unknown as { options: { workspace: string } }).options.workspace;
}

beforeAll(async () => {
	server = new WebUIServer({
		workspace: mkdtempSync(join(tmpdir(), "rt-p4-")),
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

function rpc(
	method: string,
	params: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
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

async function rest(
	path: string,
): Promise<{ status: number; body: Record<string, unknown> }> {
	const res = await fetch(`http://127.0.0.1:${port}${path}`);
	return {
		status: res.status,
		body: (await res.json()) as Record<string, unknown>,
	};
}

describe("P4 research page (issue #636)", () => {
	it("three-layer view: claims with posteriors, stage containers, transitions; scrubber replays deterministically", async () => {
		await rpc("project.create", { project_id: "pR", name: "研究项目" });
		await rpc("project.registerTask", {
			project_id: "pR",
			task_id: "tR",
			role: "main",
		});
		await rpc("research.launch", {
			task_id: "tR",
			pre_signed: { verdict: "GO", summary: "v0" },
			steps: [
				{
					event: "open-draft",
					snapshot: {
						elements: {},
						claims: [{ id: "c-mob", text: "2C4G suffices", posterior: 0.5 }],
						evidence_refs: ["sha256:" + "e".repeat(64)],
						report: {},
						deleted_nodes: [],
					},
					base_v: null,
				},
				{
					event: "attach",
					decomposition: EXTRACTION,
					decomposition_id: "dc-r",
					plan: PLAN,
				},
				{ event: "confirm" },
				{ event: "sign" },
				{ event: "research-completed" },
			],
		});
		// research activity: a claim via the hub + a stage container via the scheduler
		await rpc("chat.ingest", {
			task_id: "tR",
			kind: "claim",
			text: "2C4G suffices",
		});
		const stageLedger = new LedgerStore(
			join(workspaceFor(server), "ledger.sqlite"),
		);
		const scheduler = new ParallelDagScheduler(stageLedger, {
			maxConcurrency: 2,
		});
		scheduler.registerStages([
			{
				stage_id: "tR/s1",
				title: "recon",
				status: "pending",
				claim_ids: ["c-tR-1"],
				depends_on: [],
				assigned_worker_class: "retrieval",
				retries: 0,
				max_retries: 2,
				outputs: [],
			} satisfies ParallelStage,
			{
				stage_id: "tOther/sX",
				title: "foreign stage",
				status: "pending",
				claim_ids: [],
				depends_on: [],
				assigned_worker_class: "retrieval",
				retries: 0,
				max_retries: 2,
				outputs: [],
			} satisfies ParallelStage,
		]);
		scheduler.tick();
		const view = await rest("/api/research/tR");
		expect(view.status).toBe(200);
		const claims = view.body.claims as Record<string, Record<string, unknown>>;
		expect(Object.keys(claims).length).toBeGreaterThan(0);
		const stageIds = (view.body.stages as Array<{ stage_id: string }>).map(
			(s) => s.stage_id,
		);
		expect(stageIds.length).toBeGreaterThan(0);
		// issue #690 e2e: 别的任务的 stage 不得泄漏进本任务的画布
		expect(stageIds.every((id) => id.startsWith("tR/"))).toBe(true);
		expect(
			(view.body.transitions as Array<Record<string, unknown>>).length,
		).toBeGreaterThan(0);

		// beats = the full timeline; projection(t) is deterministic over the wire
		const beats = await rest("/api/research/tR/beats");
		const beatCount = Number((beats.body.beats as Array<unknown>).length);
		expect(beatCount).toBeGreaterThan(3);
		const mid = Math.floor(beatCount / 2);
		const atMid = await rest(`/api/research/tR/at/${mid}`);
		const atMidAgain = await rest(`/api/research/tR/at/${mid}`);
		expect(atMidAgain.body).toEqual(atMid.body); // same beat → identical projection
		const atEnd = await rest(`/api/research/tR/at/${beatCount}`);
		expect((atEnd.body.console as string[]).length).toBe(beatCount);
		expect((atMid.body.console as string[]).length).toBeLessThanOrEqual(
			beatCount,
		);

		// lineage click: a committed claim resolves ≤3 clicks (raw evidence reachable)
		const lineage = await rest("/api/research/tR/lineage/0/c-mob");
		expect(lineage.status).toBe(200);
		expect(
			(lineage.body as { steps: Array<{ layer: string }> }).steps.map(
				(s) => s.layer,
			),
		).toEqual(["canvas-node", "detail-drawer", "raw-evidence"]);
	});

	it("unknown lineage returns no-fake-lineage; research endpoints don't crash on empty tasks", async () => {
		await expect(
			rest("/api/research/tR/lineage/0/ghost"),
		).resolves.toMatchObject({ status: 200 });
		const empty = await rest("/api/research/tEmpty");
		expect(empty.status).toBe(200);
		expect(empty.body.claims).toEqual({});
	});

	it("restart durability: a fresh process reports the persisted phase from the ledger (issue #690)", async () => {
		await rpc("project.create", { project_id: "pDur", name: "重启后阶段" });
		await rpc("project.registerTask", {
			project_id: "pDur",
			task_id: "tDur",
			role: "main",
		});
		// simulate the transition trail the confirm flow wrote before a restart
		const ledger = new LedgerStore(
			join(workspaceFor(server), "ledger.sqlite"),
		);
		ledger.appendGraphEvent("task.transition", {
			id: "task-transition-dur-1",
			task_id: "tDur",
			from: "chat",
			to: "decompose",
			reason: null,
		});
		ledger.appendGraphEvent("task.transition", {
			id: "task-transition-dur-2",
			task_id: "tDur",
			from: "decompose",
			to: "research",
			reason: null,
		});
		// a cold process (restart) — its in-memory phase map is empty
		const fresh = new WebUIServer({ workspace: workspaceFor(server) });
		const freshPort = await fresh.listen();
		try {
			const socket = await new Promise<WebSocket>((resolve, reject) => {
				const s = new WebSocket(`ws://127.0.0.1:${freshPort}/ws`);
				s.on("open", () => resolve(s));
				s.on("error", reject);
			});
			const status = await new Promise<Record<string, unknown>>(
				(resolve, reject) => {
					const onMessage = (data: unknown): void => {
						const msg = JSON.parse(String(data)) as Record<string, unknown>;
						if (msg.id === 1) {
							socket.off("message", onMessage);
							if (msg.ok === true) resolve(msg.result as Record<string, unknown>);
							else reject(new Error(String(msg.error)));
						}
					};
					socket.on("message", onMessage);
					socket.send(
						JSON.stringify({ id: 1, method: "task.status", params: { task_id: "tDur" } }),
					);
				},
			);
			socket.close();
			expect(status.phase).toBe("research");
		} finally {
			await fresh.close();
		}
	});
});
