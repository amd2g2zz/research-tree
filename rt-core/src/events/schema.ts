/** Table-driven event schemas: one declarative spec per event type (issue #546).

Instead of eleven hand-written validator functions, each event type declares
its field contract; a single generic engine validates payloads against the
spec. The `Record<GraphEventType, EventSpec>` typing makes the compiler
enforce coverage of the whole vocabulary.

Spec source: the superseded Python implementation (PR #581) — field sets and
error naming carried over verbatim.
*/

export const GRAPH_EVENT_TYPES = [
  "claim.upsert",
  "claim.kill_edge",
  "stage.upsert",
  "stage.depends_on",
  "stage.contains",
  "evidence.upsert",
  "evidence.attach",
  "artifact.upsert",
  "artifact.link",
  "version.commit",
  "fork.edge",
  "provider.action",
] as const;

export type GraphEventType = (typeof GRAPH_EVENT_TYPES)[number];

export const CLAIM_SOURCES = ["user", "research"] as const;
export const CLAIM_WEIGHTS = ["make_or_break", "important", "minor"] as const;
export const VERIFY_TIERS = ["rederive", "multi-source", "verbatim", "single-source", "experiment"] as const;
export const VERDICTS = ["GO", "NO-GO", "PARK", "REFRAMED"] as const;

export const GENESIS_HASH = "0".repeat(64);

export class GraphEventError extends Error {}

export type FieldKind = "nonEmpty" | "string" | "enum" | "probability" | "integer" | "boolean";

export interface FieldSpec {
  kind: FieldKind;
  optional?: boolean;
  fallback?: boolean; // for optional booleans
  allowed?: readonly string[]; // enum
  minimum?: number; // integer
}

export interface ObjectSpec {
  fields: Readonly<Record<string, FieldSpec>>;
}

export type EventSpec =
  | { kind: "node"; object: ObjectSpec }
  | { kind: "flat"; object: ObjectSpec }
  | { kind: "pair"; firstId: string; secondId: string };

const f = (kind: FieldKind, extra: Partial<FieldSpec> = {}): FieldSpec => ({ kind, ...extra });

const CLAIM_FIELDS: ObjectSpec = {
  fields: {
    id: f("nonEmpty"),
    text: f("string"),
    source: f("enum", { allowed: CLAIM_SOURCES }),
    weight: f("enum", { allowed: CLAIM_WEIGHTS }),
    posterior: f("probability"),
    verify_tier: f("enum", { allowed: VERIFY_TIERS }),
    stale: f("boolean", { optional: true, fallback: false }),
  },
};

const STAGE_FIELDS: ObjectSpec = {
  fields: { id: f("nonEmpty"), title: f("string"), status: f("string") },
};

const EVIDENCE_FIELDS: ObjectSpec = {
  fields: { id: f("nonEmpty"), digest: f("nonEmpty"), origin: f("string") },
};

const ARTIFACT_FIELDS: ObjectSpec = {
  fields: {
    id: f("nonEmpty"),
    kind: f("string"),
    digest: f("nonEmpty"),
    deleted: f("boolean", { optional: true, fallback: false }),
  },
};

const VERSION_FIELDS: ObjectSpec = {
  fields: {
    id: f("nonEmpty"),
    task_id: f("nonEmpty"),
    v: f("integer", { minimum: 0 }),
    commit_hash: f("nonEmpty"),
    verdict: f("enum", { allowed: VERDICTS }),
    summary: f("string"),
  },
};

export const EVENT_SPECS: Record<GraphEventType, EventSpec> = {
  "claim.upsert": { kind: "node", object: CLAIM_FIELDS },
  "claim.kill_edge": { kind: "pair", firstId: "claim_id", secondId: "kill_target_id" },
  "stage.upsert": { kind: "node", object: STAGE_FIELDS },
  "stage.depends_on": { kind: "pair", firstId: "stage_id", secondId: "depends_on_id" },
  "stage.contains": { kind: "pair", firstId: "stage_id", secondId: "claim_id" },
  "evidence.upsert": { kind: "node", object: EVIDENCE_FIELDS },
  "evidence.attach": { kind: "pair", firstId: "evidence_id", secondId: "claim_id" },
  "artifact.upsert": { kind: "node", object: ARTIFACT_FIELDS },
  "artifact.link": { kind: "pair", firstId: "artifact_id", secondId: "claim_id" },
  "version.commit": { kind: "node", object: VERSION_FIELDS },
  "fork.edge": { kind: "pair", firstId: "child_version_id", secondId: "parent_version_id" },
  "provider.action": {
    kind: "flat",
    object: {
      fields: {
        id: f("nonEmpty"),
        provider: f("nonEmpty"),
        action: f("enum", { allowed: ["search", "fetch"] }),
        target: f("string"),
        outcome: f("enum", { allowed: ["ok", "error"] }),
        result_count: f("integer", { minimum: 0, optional: true }),
        bytes: f("integer", { minimum: 0, optional: true }),
      },
    },
  },
};

type Payload = Record<string, unknown>;

function isMapping(value: unknown): value is Payload {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validateField(entry: Payload, key: string, spec: FieldSpec, label: string): unknown {
  if (!(key in entry) || entry[key] === undefined || entry[key] === null) {
    // null is the canonical form of "absent" (records round-trip through JSON)
    if (spec.optional) {
      return spec.fallback ?? null;
    }
    throw new GraphEventError(`${label} missing required keys: ${JSON.stringify([key])}`);
  }
  const value = entry[key];
  switch (spec.kind) {
    case "nonEmpty":
      if (typeof value !== "string" || value === "") {
        throw new GraphEventError(`field "${key}" must be a non-empty string`);
      }
      return value;
    case "string":
      if (typeof value !== "string") {
        throw new GraphEventError(`field "${key}" must be a string`);
      }
      return value;
    case "enum":
      if (typeof value !== "string" || !(spec.allowed as readonly string[]).includes(value)) {
        throw new GraphEventError(`field "${key}" must be one of ${JSON.stringify(spec.allowed)}`);
      }
      return value;
    case "probability": {
      if (typeof value !== "number" || Number.isNaN(value)) {
        throw new GraphEventError(`field "${key}" must be a number`);
      }
      if (value < 0 || value > 1) {
        throw new GraphEventError(`field "${key}" must lie in [0, 1]`);
      }
      return value;
    }
    case "integer": {
      if (typeof value !== "number" || !Number.isInteger(value)) {
        throw new GraphEventError(`field "${key}" must be an integer`);
      }
      if (value < (spec.minimum ?? 0)) {
        throw new GraphEventError(`field "${key}" must be >= ${spec.minimum ?? 0}`);
      }
      return value;
    }
    case "boolean":
      if (typeof value !== "boolean") {
        throw new GraphEventError(`field "${key}" must be a boolean`);
      }
      return value;
  }
}

function validateObject(entry: unknown, spec: ObjectSpec, label: string): Payload {
  if (!isMapping(entry)) {
    throw new GraphEventError(`payload must be a mapping: ${label}`);
  }
  const out: Payload = {};
  for (const [key, fieldSpec] of Object.entries(spec.fields)) {
    out[key] = validateField(entry, key, fieldSpec, label);
  }
  for (const key of Object.keys(entry)) {
    if (!(key in spec.fields)) {
      throw new GraphEventError(`${label} has unexpected keys: ${JSON.stringify([key])}`);
    }
  }
  return out;
}

function validatePair(payload: Payload, spec: EventSpec & { kind: "pair" }): Payload {
  const { firstId, secondId } = spec;
  for (const key of [firstId, secondId]) {
    if (!(key in payload)) {
      throw new GraphEventError(`payload missing required keys: ${JSON.stringify([key])}`);
    }
  }
  for (const key of Object.keys(payload)) {
    if (key !== firstId && key !== secondId) {
      throw new GraphEventError(`payload has unexpected keys: ${JSON.stringify([key])}`);
    }
  }
  const first = payload[firstId];
  const second = payload[secondId];
  for (const [key, value] of [
    [firstId, first],
    [secondId, second],
  ] as const) {
    if (typeof value !== "string" || value === "") {
      throw new GraphEventError(`field "${key}" must be a non-empty string`);
    }
  }
  if (first === second) {
    throw new GraphEventError(`ids must be distinct: "${first}" == "${second}"`);
  }
  return { [firstId]: first, [secondId]: second };
}

/** Validate one graph event and return its normalized payload. */
export function validateGraphEvent(eventType: unknown, payload: unknown): Payload {
  if (
    typeof eventType !== "string" ||
    !(GRAPH_EVENT_TYPES as readonly string[]).includes(eventType)
  ) {
    throw new GraphEventError(`unknown graph event type: ${String(eventType)}`);
  }
  if (!isMapping(payload)) {
    throw new GraphEventError("payload must be a mapping");
  }
  const spec = EVENT_SPECS[eventType as GraphEventType];
  const key = nodeKey(eventType as GraphEventType);
  return spec.kind === "node"
    ? { [key]: validateObject(payload[key], spec.object, key) }
    : spec.kind === "flat"
      ? validateObject(payload, spec.object, key)
      : validatePair(payload, spec);
}

function nodeKey(eventType: GraphEventType): string {
  return eventType.split(".")[0]!;
}
