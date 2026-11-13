/** Real-flow helpers (issue #655): the pieces that make the WebUI actually
 * usable without any fixture injection.

- **extractionFromChat prompt** — the hub transcript goes to the pi session;
  the model returns six-element JSON; quotes are mapped BACK to the
  transcript mechanically (溯源律): an element whose quote cannot be found
  in the transcript keeps no provenance and is dropped by
  parseDecomposition — honestly counted, never fabricated.
- **mechanical plan** — from the confirmed decomposition's claims_preview:
  one stage per claim (no LLM; scheduling is engine work).
- **start steps** — the real walk assembly (open-draft with preview claims →
  attach confirmed decomposition → confirm → sign), no fixtures.
*/

import type { DecompositionElements } from "../../rt-core/src/decomposition/engine.js";

export interface TranscriptMessage {
	seq: number;
	role: string;
	kind: string;
	text: string;
	created_at: string;
}

export function extractionPrompt(messages: TranscriptMessage[]): string {
	const transcript = messages
		.filter((m) => m.role === "user" || m.role === "system")
		.map((m) => `[${m.seq}] ${m.text}`)
		.join("\n");
	return (
		"你是研究分解器。把下面的对话分解为六要素 JSON（只输出 JSON，不要别的文字）：\n" +
		'{"requirements":[{"text":"...","quote":"原话片段"}],' +
		'"constraints":[{"text":"...","quote":"...","hardness":"hard|guessed"}],' +
		'"background":[{"text":"...","quote":"..."}],' +
		'"intents":[{"text":"...","quote":"..."}],' +
		'"refusals":[{"text":"...","quote":"..."}],' +
		'"difficulties":[{"text":"...","quote":"...","kill_candidates":["c-..."]}],' +
		'"claims_preview":[{"id":"c-...","text":"...","kill_condition":"..."}]}\n' +
		"规则：每条要素的 quote 必须逐字来自对话原句（溯源律）；宁多勿漏；refusals 可以为空数组。\n\n对话：\n" +
		transcript
	);
}

/** Parse the model's six-element JSON, mapping each quote back to the
 * transcript message that contains it (provenance = mechanical, not model-claimed). */
export function parseExtraction(
	stdout: string,
	messages: TranscriptMessage[],
): DecompositionElements {
	const match = /\{[\s\S]*\}/.exec(stdout);
	if (match === null) {
		throw new Error("extraction returned no JSON object");
	}
	let raw: Record<string, unknown>;
	try {
		raw = JSON.parse(match[0]) as Record<string, unknown>;
	} catch {
		throw new Error(
			`extraction returned malformed JSON: ${match[0].slice(0, 60)}`,
		);
	}
	const findSeq = (quote: unknown): number | null => {
		if (typeof quote !== "string" || quote === "") {
			return null;
		}
		const hit = messages.find(
			(m) => m.role === "user" && m.text.includes(quote),
		);
		return hit !== undefined ? hit.seq : null;
	};
	const withProvenance = (cls: string): Array<Record<string, unknown>> => {
		const list = raw[cls];
		if (!Array.isArray(list)) {
			return [];
		}
		return list
			.filter(
				(el): el is Record<string, unknown> =>
					typeof el === "object" && el !== null,
			)
			.map((el) => {
				const seq = findSeq(el.quote);
				return seq !== null
					? {
							...el,
							source: {
								kind: "chat-message",
								ref: `msg:${seq}`,
								quote: el.quote,
							},
						}
					: el; // no provenance → dropped by parseDecomposition, counted
			});
	};
	const preview = raw.claims_preview;
	return {
		requirements: withProvenance("requirements"),
		constraints: withProvenance("constraints"),
		background: withProvenance("background"),
		intents: withProvenance("intents"),
		refusals: withProvenance("refusals"),
		difficulties: withProvenance("difficulties"),
		claims_preview: Array.isArray(preview)
			? (preview.filter((el) => typeof el === "object" && el !== null) as Array<
					Record<string, unknown>
				>)
			: [],
	} as DecompositionElements;
}

/** Mechanical plan from claims_preview: one stage per claim (依赖留空 —
 * the DAG grows from evidence, not from invented sequencing). */
export function mechanicalPlan(elements: Record<string, unknown>): {
	plan_id: string;
	stages: Array<{
		id: string;
		title: string;
		claim_ids: string[];
		depends_on: string[];
	}>;
	budget: { capMs: number };
	yaw_checks: Array<{ slot: string; mode: string }>;
} {
	const preview = Array.isArray(elements.claims_preview)
		? (elements.claims_preview as Array<Record<string, unknown>>)
		: [];
	return {
		plan_id: `plan-${Date.now().toString(36)}`,
		stages: preview.map((claim, i) => ({
			id: `stage-${String(claim.id ?? i)}`,
			title: `verify: ${String(claim.text ?? claim.id ?? i)}`,
			claim_ids: [String(claim.id ?? `c-${i}`)],
			depends_on: [],
		})),
		budget: { capMs: 12 * 3600 * 1000 },
		yaw_checks: [
			{ slot: "plan-level", mode: "auto" },
			{ slot: "problem-level", mode: "human" },
			{ slot: "knowledge-level", mode: "auto" },
		],
	};
}
