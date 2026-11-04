/** chat.turn tests (issue #660): the agent RESPONDS — reply + proactive
 * questions + real recon through the provider port; everything lands as
 * transcript data; fail-closed without a keyed session. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import type {
	DataSourceProvider,
	SearchResult,
} from "../../rt-core/src/providers/types.js";
import { buildTurnPrompt, parseTurnOutput } from "../src/chat-turn.js";
import { WebUIServer } from "../src/server.js";

const TURN_JSON = JSON.stringify({
	kind: "preference",
	converged: true,
	reply:
		"「开数据标注公司」目前太虚：没说目标客户、标注类型和起步规模。我先把它收敛成一个可调研的命题。",
	questions: [
		"目标客户是AI lab还是企业内部标注需求？",
		"起步资金和人力规模有硬性上限吗？",
	],
	recon: { query: "数据标注公司 2025 市场规模" },
});

const SEARCH_RESULTS: SearchResult[] = [
	{
		title: "2025 数据标注市场报告",
		url: "https://example.com/r",
		snippet: "市场规模 XX 亿，年增 20%",
	},
];

class FakeProvider implements DataSourceProvider {
	readonly queries: string[] = [];
	readonly manifest = {
		name: "anysearch",
		capabilities: { search: true, fetch: false },
		kinds: ["web-search"],
		description: "fake",
		usage: "docs/providers/anysearch.md",
	};
	async search(query: { query: string }): Promise<SearchResult[]> {
		this.queries.push(query.query);
		return SEARCH_RESULTS;
	}
	async fetch(): Promise<never> {
		throw new Error("not implemented");
	}
}

let server: WebUIServer;
let port: number;
let ws: WebSocket;
let provider: FakeProvider;
let nextId = 1;

beforeAll(async () => {
	const piDir = mkdtempSync(join(tmpdir(), "rt-ct-pi-"));
	writeFileSync(
		join(piDir, "models.json"),
		JSON.stringify({
			providers: {
				deepseek: { apiKey: "k", models: [{ id: "deepseek-flash" }] },
			},
		}),
	);
	writeFileSync(
		join(piDir, "models-store.json"),
		JSON.stringify({ default: "deepseek/deepseek-flash" }),
	);
	provider = new FakeProvider();
	server = new WebUIServer({
		workspace: mkdtempSync(join(tmpdir(), "rt-ct-")),
		piConfigDir: piDir,
		piRunner: () => TURN_JSON, // one call per turn (#674): kind + reply in one JSON
		provider,
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

describe("chat.turn conversational loop (issue #660)", () => {
	it("prompt carries the transcript and demands a substantive reply + 歧视性优先提问策略", () => {
		const prompt = buildTurnPrompt([
			{
				seq: 1,
				role: "user",
				kind: "preference",
				text: "我想开个数据标注公司",
				created_at: "t",
			},
			{ seq: 2, role: "rt", kind: "reply", text: "回执", created_at: "t" },
		]);
		expect(prompt).toContain("[1][user] 我想开个数据标注公司");
		expect(prompt).toContain("歧视性");
		expect(prompt).toContain('"recon"');
	});

	it("parse fails closed on empty reply / bad kind / garbage", () => {
		expect(() =>
			parseTurnOutput('{"kind":"claim","reply":"","questions":[]}'),
		).toThrow(/substantive reply/);
		expect(() => parseTurnOutput('{"reply":"x","questions":[]}')).toThrow(
			/unusable kind/,
		); // kind required in the same call
		expect(() => parseTurnOutput("随便说说")).toThrow(/no JSON/);
		const ok = parseTurnOutput(TURN_JSON);
		expect(ok.kind).toBe("preference");
		expect(ok.converged).toBe(true); // #679: 语义收敛驱动确认阶段
		expect(ok.questions).toHaveLength(2);
		expect(ok.recon?.query).toContain("数据标注");
	});

	it("full turn: user utterance → reply+questions stored, recon executed through the provider port, audit lands", async () => {
		await rpc("project.create", { project_id: "pT", name: "对话回路" });
		await rpc("project.registerTask", {
			project_id: "pT",
			task_id: "tT",
			role: "main",
		});

		const result = await rpc("chat.turn", {
			task_id: "tT",
			text: "我想开个数据标注公司",
		});
		expect(result.reply as string).toContain("太虚");
		expect((result.questions as string[]).length).toBe(2);
		expect(result.classified_by).toBe("pi-session"); // single-call judgment
		expect(
			(result.recon_results as Array<Record<string, unknown>>)[0],
		).toMatchObject({ title: "2025 数据标注市场报告" });
		expect(provider.queries[0]).toContain("数据标注公司"); // real provider port execution

		// transcript holds user + recon + reply + questions (all as data)
		const history = (await rpc("chat.history", { task_id: "tT" }))
			.messages as Array<Record<string, unknown>>;
		const kinds = history.filter((m) => m.role === "rt").map((m) => m.kind);
		expect(kinds).toContain("recon");
		expect(kinds).toContain("reply");
		expect(kinds.filter((k) => k === "question")).toHaveLength(2);

		// provider audit event for the recon search
		const audit = server
			.ledgerForTests()
			.graphEvents()
			.filter(
				(e) => (e.payload as Record<string, unknown>).provider === "anysearch",
			);
		expect(audit.length).toBe(1);

		// classification receipt still parallel (the user message carries it)
		const userMsg = history.find((m) => m.role === "user");
		expect(JSON.parse(String(userMsg?.receipt_json)).classified_by).toBe(
			"pi-session",
		);
	});

	it("fail-closed without a keyed session (no simulated conversation)", async () => {
		const cold = new WebUIServer({
			workspace: mkdtempSync(join(tmpdir(), "rt-ct-cold-")),
			piConfigDir: mkdtempSync(join(tmpdir(), "rt-ct-cold-pi-")),
		});
		const coldPort = await cold.listen();
		const coldWs = await new Promise<WebSocket>((resolve, reject) => {
			const s = new WebSocket(`ws://127.0.0.1:${coldPort}/ws`);
			s.on("open", () => resolve(s));
			s.on("error", reject);
		});
		await rpcOn(coldWs, "project.create", { project_id: "pC", name: "n" });
		await rpcOn(coldWs, "project.registerTask", {
			project_id: "pC",
			task_id: "tC",
			role: "main",
		});
		await expect(
			rpcOn(coldWs, "chat.turn", { task_id: "tC", text: "想法" }),
		).rejects.toThrow(/keyed session not ready/);
		coldWs.close();
		await cold.close();
	});
});

function rpcOn(
	ws: WebSocket,
	method: string,
	params: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
	const id = Date.now() + Math.random();
	return new Promise((resolve, reject) => {
		const on = (data: unknown): void => {
			const msg = JSON.parse(String(data)) as Record<string, unknown>;
			if (msg.id === id) {
				ws.off("message", on);
				msg.ok === true
					? resolve(msg.result as Record<string, unknown>)
					: reject(new Error(String(msg.error)));
			}
		};
		ws.on("message", on);
		ws.send(JSON.stringify({ id, method, params }));
	});
}
