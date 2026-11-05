/** Shared view-model types for the WebUI (issue #690). Server shapes live in
 * webui-server/src/server.ts; these are the display-side projections. */

export interface Project {
	project_id: string;
	name: string;
	status: string;
	vitals: {
		research_lines: number;
		latest: { v: number; verdict: string; commit_hash: string } | null;
		elapsed_ms: number;
	};
	lines: Array<{ task_id: string; role: string }>;
}

export interface ChatMsg {
	seq: number;
	role: string;
	kind: string;
	text: string;
	receipt_json: string | null;
}

export interface StageInfo {
	stage_id: string;
	title: string;
	status: string;
	claim_ids: string[];
	depends_on: string[];
	assigned_worker_class?: string;
}

export interface MindNode {
	id: string;
	text: string;
	branch?: string;
	quote?: string;
	children: MindNode[];
}

export interface ClaimView {
	text: string;
	posterior: number;
	state?: string;
	weight?: string;
	verify_tier?: string;
}

/** GET /api/research/:taskId — three-layer canvas projection + stage table. */
export interface ResearchView {
	question: unknown;
	claims: Record<string, ClaimView>;
	stages: StageInfo[];
}

/** GET /api/config/pi — pi config readiness (no key material). */
export interface PiConfigSummary {
	config_path: string;
	present: boolean;
	default_model: string | null;
	keyed_session_ready: boolean;
	readiness: {
		has_provider_key: boolean;
		has_model: boolean;
		has_default_model: boolean;
	};
	follows_pi_default: boolean;
}

/** 三步流视图：①对话 ②思维导图确认 ③调研画布（docs/product/05）。 */
export type View = "chat" | "mindmap" | "research";

export type Kind = "auto" | "preference" | "claim" | "guess" | "branch";
