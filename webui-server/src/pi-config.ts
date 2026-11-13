/** pi config read/write (issues #632/#638/#655).

The WebUI NEVER maintains a parallel model/API config: **pi's own config
directory is the single source of truth** (~/.pi/agent/):

- **models.json** — pi's real provider registry: `providers.<id> =
  {name, baseUrl, api, apiKey, models:[{id,name,...}]}`. This is what the
  settings page reads (key values masked) and writes (schema-compatible
  upsert). When the user has NOT overridden anything, the product follows
  **pi agent's own defaults** — the UI says so, it never requires an
  rt-side choice.
- **models-store.json** — optional default-model override marker.
- **auth.json** — legacy auth store, still surfaced as provider names.

Key material never reaches the WebSocket, the logs, or the audit trail.
Files that are missing or unparsable degrade gracefully — a config probe
never crashes the server.
*/

import {
	existsSync,
	mkdirSync,
	readFileSync,
	renameSync,
	writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface PiModelInfo {
	/** "<provider>/<model-id>" */
	id: string;
	name: string;
	provider: string;
}

export interface PiConfigSummary {
	config_path: string;
	present: boolean;
	/** rt-side override marker; when null the product follows pi agent's own default */
	default_model: string | null;
	/** flat model list from models.json providers (no key material) */
	models: PiModelInfo[];
	/** provider ids carrying a key (models.json first, legacy auth.json fallback) */
	auth_providers: string[];
	/** provider ids present in models.json regardless of key */
	providers: string[];
	keyed_session_ready: boolean;
	readiness: {
		has_provider_key: boolean;
		has_model: boolean;
		has_default_model: boolean;
	};
	/** true when nothing is overridden rt-side — follow pi agent's own config */
	follows_pi_default: boolean;
}

type Json = Record<string, unknown>;

function readJson(path: string): Json | null {
	if (!existsSync(path)) {
		return null;
	}
	try {
		const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
		return typeof parsed === "object" && parsed !== null
			? (parsed as Json)
			: null;
	} catch {
		return null;
	}
}

interface ProviderEntry {
	name?: string;
	baseUrl?: string;
	api?: string;
	apiKey?: string;
	models?: Array<{ id?: string; name?: string }>;
}

function extractFromModelsJson(modelsJson: Json | null): {
	models: PiModelInfo[];
	providers: string[];
	keyedProviders: string[];
} {
	const providersObj = modelsJson?.providers;
	const models: PiModelInfo[] = [];
	const providers: string[] = [];
	const keyedProviders: string[] = [];
	if (typeof providersObj === "object" && providersObj !== null) {
		for (const [id, entry] of Object.entries(
			providersObj as Record<string, unknown>,
		)) {
			providers.push(id);
			const p = entry as ProviderEntry;
			if (typeof p.apiKey === "string" && p.apiKey !== "") {
				keyedProviders.push(id);
			}
			for (const model of Array.isArray(p.models) ? p.models : []) {
				if (typeof model?.id === "string") {
					models.push({
						id: `${id}/${model.id}`,
						name: model.name ?? model.id,
						provider: id,
					});
				}
			}
		}
	}
	return { models, providers, keyedProviders };
}

export function readPiConfig(
	dir: string = join(homedir(), ".pi", "agent"),
): PiConfigSummary {
	const modelsJson = readJson(join(dir, "models.json"));
	const store = readJson(join(dir, "models-store.json"));
	const auth = readJson(join(dir, "auth.json"));
	const { models, providers, keyedProviders } =
		extractFromModelsJson(modelsJson);
	const authProviders = auth !== null ? Object.keys(auth) : [];
	const def = store?.default;
	const defaultModel = typeof def === "string" && def !== "" ? def : null;
	const hasProviderKey =
		keyedProviders.length > 0 ||
		authProviders.some((p) => {
			const entry = auth?.[p];
			return (
				typeof entry === "object" &&
				entry !== null &&
				Object.keys(entry as Json).length > 0
			);
		});
	const hasModel = models.length > 0;
	return {
		config_path: dir,
		present: modelsJson !== null || store !== null || auth !== null,
		default_model: defaultModel,
		models,
		auth_providers: keyedProviders.length > 0 ? keyedProviders : authProviders,
		providers,
		keyed_session_ready: hasProviderKey && hasModel,
		readiness: {
			has_provider_key: hasProviderKey,
			has_model: hasModel,
			has_default_model: defaultModel !== null,
		},
		follows_pi_default: defaultModel === null,
	};
}

export class ConfigWriteError extends Error {}

function atomicWrite(path: string, body: string): void {
	const tmp = `${path}.tmp-${process.pid}`;
	writeFileSync(tmp, body);
	renameSync(tmp, path);
}

/** Upsert a provider entry INTO pi's own models.json (schema-compatible
 * with pi's provider registry). Returns what was written — never the key. */
export function writeProviderKey(
	dir: string | undefined,
	input: {
		provider: string;
		api_key: string;
		name?: string;
		baseUrl?: string;
		api?: string;
		model_id?: string;
		model_name?: string;
	},
): { saved: true; provider: string } {
	const base = dir ?? join(homedir(), ".pi", "agent");
	const provider = input.provider.trim();
	if (provider === "" || !/^[A-Za-z0-9_-]+$/.test(provider)) {
		throw new ConfigWriteError(`invalid provider name: ${input.provider}`);
	}
	if (input.api_key.trim() === "") {
		throw new ConfigWriteError("api key must not be empty");
	}
	mkdirSync(base, { recursive: true });
	const path = join(base, "models.json");
	const modelsJson = readJson(path) ?? {};
	const providersObj = (
		typeof modelsJson.providers === "object" && modelsJson.providers !== null
			? (modelsJson.providers as Json)
			: {}
	) as Record<string, unknown>;
	const existing = (providersObj[provider] ?? {}) as ProviderEntry;
	const models = Array.isArray(existing.models) ? existing.models : [];
	if (
		input.model_id !== undefined &&
		input.model_id.trim() !== "" &&
		!models.some((m) => m.id === input.model_id)
	) {
		models.push({
			id: input.model_id.trim(),
			name: input.model_name ?? input.model_id.trim(),
		});
	}
	providersObj[provider] = {
		name: input.name ?? existing.name ?? provider,
		baseUrl: input.baseUrl ?? existing.baseUrl ?? "",
		api: input.api ?? existing.api ?? "openai-completions",
		apiKey: input.api_key,
		models,
	};
	modelsJson.providers = providersObj;
	atomicWrite(path, JSON.stringify(modelsJson, null, 2));
	const verified = readJson(path);
	const check = (verified?.providers as Json | undefined)?.[provider] as
		| ProviderEntry
		| undefined;
	if (check?.apiKey !== input.api_key) {
		throw new ConfigWriteError(
			`write-then-read verification failed for provider ${provider}`,
		);
	}
	return { saved: true, provider };
}

/** rt-side default-model override marker (models-store.json). When unset,
 * the product follows pi agent's own default — disclosed as such. */
export function writeDefaultModel(
	dir: string | undefined,
	model: string,
): { saved: true; default_model: string } {
	if (model.trim() === "") {
		throw new ConfigWriteError("model must not be empty");
	}
	const base = dir ?? join(homedir(), ".pi", "agent");
	mkdirSync(base, { recursive: true });
	const path = join(base, "models-store.json");
	const store = readJson(path) ?? {};
	store.default = model.trim();
	atomicWrite(path, JSON.stringify(store, null, 2));
	const summary = readPiConfig(base);
	if (summary.default_model !== model.trim()) {
		throw new ConfigWriteError(
			`write-then-read verification failed for model ${model}`,
		);
	}
	return { saved: true, default_model: model.trim() };
}
