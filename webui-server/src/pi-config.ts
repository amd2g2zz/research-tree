/** pi config read path (issue #632 spike, config single-source baseline).

The WebUI NEVER maintains a parallel model/API config (2026-10-30 pi-only
ruling, user ruling 2026-10-31): pi's own config directory is the single
source of truth. This module READS it — `~/.pi/agent/` by default:

- models-store.json → available models + default selection
- auth.json → **provider names only, never key values** (masking is the red
  line: key material must not reach the WebSocket or any log)

Files that are missing or unparsable degrade to nulls — a config probe never
crashes the server.
*/

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface PiConfigSummary {
  config_path: string;
  present: boolean;
  default_model: string | null;
  models: string[];
  /** provider names from auth.json — key VALUES are never read out */
  auth_providers: string[];
}

type Json = Record<string, unknown>;

function readJson(path: string): Json | null {
  if (!existsSync(path)) {
    return null;
  }
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
    return typeof parsed === "object" && parsed !== null ? (parsed as Json) : null;
  } catch {
    return null;
  }
}

/** Defensive extraction — the store's exact shape is pi-version-dependent. */
function extractModels(store: Json): { models: string[]; default_model: string | null } {
  const models: string[] = [];
  const raw = store.models;
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      if (typeof entry === "string") {
        models.push(entry);
      } else if (typeof entry === "object" && entry !== null) {
        const id = (entry as Json).id ?? (entry as Json).model;
        if (typeof id === "string") {
          models.push(id);
        }
      }
    }
  } else if (typeof raw === "object" && raw !== null) {
    models.push(...Object.keys(raw as Json));
  }
  const def = store.default ?? store.default_model ?? store.current;
  return { models, default_model: typeof def === "string" ? def : (models[0] ?? null) };
}

export function readPiConfig(dir: string = join(homedir(), ".pi", "agent")): PiConfigSummary {
  const store = readJson(join(dir, "models-store.json"));
  const auth = readJson(join(dir, "auth.json"));
  const models = store !== null ? extractModels(store) : { models: [], default_model: null };
  return {
    config_path: dir,
    present: store !== null || auth !== null,
    default_model: models.default_model,
    models: models.models,
    // names only — values (API keys) are never surfaced
    auth_providers: auth !== null ? Object.keys(auth) : [],
  };
}

export class ConfigWriteError extends Error {}

function atomicWrite(path: string, body: string): void {
  // tmp + rename: a half-written pi config would be worse than an old one
  const tmp = `${path}.tmp-${process.pid}`;
  writeFileSync(tmp, body);
  renameSync(tmp, path);
}

/** Write path (issue #638): pi's own files are the ONLY thing modified — the
 * WebUI keeps no parallel copy. Returns what was written, never key values. */
export function writeProviderKey(dir: string | undefined, provider: string, apiKey: string): { saved: true; provider: string } {
  const base = dir ?? join(homedir(), ".pi", "agent");
  if (provider.trim() === "" || !/^[A-Za-z0-9_-]+$/.test(provider)) {
    throw new ConfigWriteError(`invalid provider name: ${provider}`);
  }
  if (apiKey.trim() === "") {
    throw new ConfigWriteError("api key must not be empty");
  }
  const path = join(base, "auth.json");
  const auth = readJson(path) ?? {};
  mkdirSync(base, { recursive: true });
  auth[provider] = { ...(auth[provider] as Json | undefined), api_key: apiKey };
  atomicWrite(path, JSON.stringify(auth, null, 2));
  // write-then-read verification (the read path masks — verify the file, not the summary)
  const verified = readJson(path);
  if (verified === null || (verified[provider] as Json | undefined)?.api_key !== apiKey) {
    throw new ConfigWriteError(`write-then-read verification failed for provider ${provider}`);
  }
  return { saved: true, provider };
}

export function writeDefaultModel(dir: string | undefined, model: string): { saved: true; default_model: string } {
  const base = dir ?? join(homedir(), ".pi", "agent");
  if (model.trim() === "") {
    throw new ConfigWriteError("model must not be empty");
  }
  mkdirSync(base, { recursive: true });
  const path = join(base, "models-store.json");
  const store = readJson(path) ?? {};
  store.default = model;
  if (!Array.isArray(store.models)) {
    store.models = [];
  }
  if (!(store.models as string[]).includes(model)) {
    (store.models as string[]).push(model);
  }
  atomicWrite(path, JSON.stringify(store, null, 2));
  const summary = readPiConfig(dir);
  if (summary.default_model !== model) {
    throw new ConfigWriteError(`write-then-read verification failed for model ${model}`);
  }
  return { saved: true, default_model: model };
}
