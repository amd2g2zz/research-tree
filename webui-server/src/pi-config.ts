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

import { existsSync, readFileSync } from "node:fs";
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
