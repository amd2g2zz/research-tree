/** P3 decomposition page tests (issue #635): draft → provenance-bound card
 * editing (确认前) → checklist gate → confirm freezes the constitution.
 * The extraction arrives from the LLM side (pi session); tests inject it
 * (mock boundary per the #607 precedent). */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { WebUIServer } from "../src/server.js";

const SOURCE = { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" };
const FULL_EXTRACTION = {
	requirements: [{ text: "deploy on 2C4G fast", source: SOURCE }],
	constraints: [
		{ text: "2C4G is a guess", source: SOURCE, hardness: "guessed" },
		{ text: "must ship this quarter", source: SOURCE },
	],
	background: [{ text: "pilot feedback", source: SOURCE }],
	intents: [{ text: "ship fast", source: SOURCE }],
	refusals: [],
	difficulties: [
		{ text: "2C4G memory ceiling", source: SOURCE, kill_candidates: ["c-mob"] },
	],
	claims_preview: [
		{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" },
	],
};
const PLAN = {
	plan_id: "plan-p3",
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
		workspace: mkdtempSync(join(tmpdir(), "rt-p3-")),
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

describe("P3 decomposition page (issue #635)", () => {
	it("prepare saves a DRAFT with the mechanical checklist; gaps block confirm", async () => {
		await rpc("project.create", { project_id: "p3", name: "分解项目" });
		await rpc("project.registerTask", {
			project_id: "p3",
			task_id: "t3",
			role: "main",
		});

		// an incomplete extraction drafts fine — the checklist names the gaps
		const draft = await rpc("decompose.prepare", {
			task_id: "t3",
			decomposition_id: "dc-p3",
			extraction: { requirements: [{ text: "fast", source: SOURCE }] },
		});
		expect((draft.checklist as { complete: boolean }).complete).toBe(false);
		expect(draft.checklist).toHaveProperty("gaps");

		// confirmation blocked by the pre-registration gap (engine gate, verbatim)
		await expect(
			rpc("decompose.confirm", { task_id: "t3", decomposition_id: "dc-p3" }),
		).rejects.toThrow(/pre-registration gap/);

		// unsourceable elements are dropped by the 溯源律 before persist — and the
		// checklist honestly names the resulting gap (requirements became empty)
		const withPhantom = await rpc("decompose.prepare", {
			task_id: "t3",
			decomposition_id: "dc-p3b",
			extraction: {
				requirements: [{ text: "no provenance" }],
				constraints: [{ text: "sourced", source: SOURCE }],
				background: [{ text: "b", source: SOURCE }],
				intents: [{ text: "i", source: SOURCE }],
				refusals: [{ text: "r", source: SOURCE }],
				difficulties: [{ text: "d", source: SOURCE, kill_candidates: ["c"] }],
			},
		});
		expect(withPhantom.dropped).toBe(1);
		const phantomChecklist = withPhantom.checklist as {
			complete: boolean;
			gaps: string[];
		};
		expect(phantomChecklist.complete).toBe(false);
		expect(phantomChecklist.gaps).toContain("requirements");
	});

	it("card editing before confirm re-drafts; after confirm it is frozen (major pivot)", async () => {
		await rpc("project.create", { project_id: "p4", name: "编辑项目" });
		await rpc("project.registerTask", {
			project_id: "p4",
			task_id: "t4",
			role: "main",
		});
		const prepared = await rpc("decompose.prepare", {
			task_id: "t4",
			decomposition_id: "dc-p4",
			extraction: FULL_EXTRACTION,
			refusals_note: "none",
		});
		expect((prepared.checklist as { complete: boolean }).complete).toBe(true);

		// 编辑权在确认前: delete the guessed constraint, checklist still complete
		const edited = await rpc("decompose.removeElement", {
			task_id: "t4",
			decomposition_id: "dc-p4",
			element_class: "constraints",
			index: 0,
		});
		const editedElements = edited.elements as { constraints: unknown[] };
		expect(editedElements.constraints).toHaveLength(1); // 2 → 1, checklist stays complete

		// confirm freezes the set
		await rpc("decompose.confirm", {
			task_id: "t4",
			decomposition_id: "dc-p4",
		});
		const row = await rpc("decompose.get", {
			task_id: "t4",
			decomposition_id: "dc-p4",
		});
		expect(row.status).toBe("confirmed");

		// post-confirmation editing is a major pivot — rejected
		await expect(
			rpc("decompose.removeElement", {
				task_id: "t4",
				decomposition_id: "dc-p4",
				element_class: "requirements",
				index: 0,
			}),
		).rejects.toThrow(/major pivot/);
	});

	it("confirm wires the machine; research.launch runs without re-attaching", async () => {
		await rpc("project.create", { project_id: "p5", name: "确认项目" });
		await rpc("project.registerTask", {
			project_id: "p5",
			task_id: "t5",
			role: "main",
		});
		await rpc("decompose.prepare", {
			task_id: "t5",
			decomposition_id: "dc-p5",
			extraction: FULL_EXTRACTION,
			refusals_note: "none",
		});
		const confirmed = await rpc("decompose.confirm", {
			task_id: "t5",
			decomposition_id: "dc-p5",
		});
		expect(confirmed.confirmed).toBe(true);

		// the walk with the SAME decomposition id works (already attached by confirm)
		const launch = await rpc("research.launch", {
			task_id: "t5",
			pre_signed: { verdict: "GO", summary: "p3 walk" },
			steps: [
				{
					event: "open-draft",
					snapshot: {
						elements: {},
						claims: [],
						evidence_refs: [],
						report: {},
						deleted_nodes: [],
					},
					base_v: null,
				},
				{
					event: "attach",
					decomposition: FULL_EXTRACTION,
					decomposition_id: "dc-p5",
					plan: PLAN,
				},
				{ event: "confirm" },
				{ event: "sign" },
				{ event: "research-completed" },
			],
		});
		expect(launch.outcome).toBe("success");
	});
});
