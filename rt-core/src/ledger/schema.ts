/** v2 ledger surface vocabulary + table-driven payload specs (issue #547).

Six ledger tables from docs/product/02-architecture.md §存储扩展, expressed as
declarative specs validated by one generic engine (same pattern as the event
schemas): fields carry kind/optional/bounds; every violation is named.

Vocabularies shared with the event stream are imported from events/schema.js
(single source: CLAIM_SOURCES / CLAIM_WEIGHTS / VERIFY_TIERS). Soft delete for
claims (deleted_at) keeps 产物删除 auditable and snapshot-addressable.
*/

import {
  CLAIM_SOURCES,
  CLAIM_WEIGHTS,
  VERIFY_TIERS,
} from "../events/schema.js";
import { LedgerIntegrityError as LedgerSurfaceError } from "../store/integrity.js";

export const HYPOTHESIS_STATUSES = ["open", "on_trial", "survived", "refuted"] as const;
export const EXPERIMENT_STATUSES = ["registered", "running", "stopped", "gated"] as const;
export const DECOMPOSITION_STATUSES = ["draft", "confirmed", "superseded"] as const;

export type FieldKind =
  | "nonEmpty"
  | "string"
  | "enum"
  | "probability"
  | "integer"
  | "boolean"
  | "killEdgeList"
  | "stringList"
  | "mapping"
  | "optionalMapping"
  | "mappingList"
  | "optionalNonNegativeNumber";

export interface FieldSpec {
  kind: FieldKind;
  optional?: boolean;
  allowed?: readonly string[];
  minimum?: number;
}

export interface SurfaceSpec {
  idColumn: string;
  fields: Readonly<Record<string, FieldSpec>>;
  /** columns stored as canonical JSON text */
  json: readonly string[];
  /** columns stored as 0/1 integers, returned as booleans */
  booleans: readonly string[];
}

const f = (kind: FieldKind, extra: Partial<FieldSpec> = {}): FieldSpec => ({ kind, ...extra });

export const SURFACE_SPECS: Record<string, SurfaceSpec> = {
  claims: {
    idColumn: "claim_id",
    fields: {
      claim_id: f("nonEmpty"),
      text: f("string"),
      source: f("enum", { allowed: CLAIM_SOURCES }),
      weight: f("enum", { allowed: CLAIM_WEIGHTS }),
      posterior: f("probability"),
      verify_tier: f("enum", { allowed: VERIFY_TIERS }),
      kill_edges: f("killEdgeList"),
      incentive_flag: f("boolean"),
    },
    json: ["kill_edges"],
    booleans: ["incentive_flag"],
  },
  sources: {
    idColumn: "source_id",
    fields: {
      source_id: f("nonEmpty"),
      origin: f("nonEmpty"),
      kind: f("string"),
      reliability: f("probability"),
      incentive_vector: f("stringList"),
      astroturf_flag: f("boolean"),
      provenance: f("mapping"),
    },
    json: ["incentive_vector", "provenance"],
    booleans: ["astroturf_flag"],
  },
  hypotheses: {
    idColumn: "hypothesis_id",
    fields: {
      hypothesis_id: f("nonEmpty"),
      text: f("string"),
      status: f("enum", { allowed: HYPOTHESIS_STATUSES }),
      review: f("optionalMapping"),
    },
    json: ["review"],
    booleans: [],
  },
  directions: {
    idColumn: "direction_id",
    fields: {
      direction_id: f("nonEmpty"),
      round: f("integer", { minimum: 0 }),
      value_posterior: f("probability"),
      budget_allocation: f("probability"),
      history: f("mappingList"),
    },
    json: ["history"],
    booleans: [],
  },
  experiments: {
    idColumn: "experiment_id",
    fields: {
      experiment_id: f("nonEmpty"),
      status: f("enum", { allowed: EXPERIMENT_STATUSES }),
      preregistration: f("mapping"),
      stop_state: f("optionalMapping"),
      cost: f("optionalNonNegativeNumber"),
    },
    json: ["preregistration", "stop_state"],
    booleans: [],
  },
  decompositions: {
    idColumn: "decomposition_id",
    fields: {
      decomposition_id: f("nonEmpty"),
      elements: f("mapping"),
      checklist_state: f("mapping"),
      status: f("enum", { allowed: DECOMPOSITION_STATUSES }),
    },
    json: ["elements", "checklist_state"],
    booleans: [],
  },
};

type Payload = Record<string, unknown>;

function isMapping(value: unknown): value is Payload {
  return value !== null && typeof value !== "undefined" && typeof value === "object" && !Array.isArray(value);
}

function validateField(
  entry: Payload,
  key: string,
  spec: FieldSpec,
  label: string,
  all: Payload,
): unknown {
  if (!(key in entry) || entry[key] === undefined) {
    if (spec.optional) {
      return null;
    }
    throw new LedgerSurfaceError(`${label} missing required keys: ${JSON.stringify([key])}`);
  }
  const value = entry[key];
  switch (spec.kind) {
    case "nonEmpty":
      if (typeof value !== "string" || value === "") {
        throw new LedgerSurfaceError(`field "${key}" must be a non-empty string`);
      }
      return value;
    case "string":
      if (typeof value !== "string") {
        throw new LedgerSurfaceError(`field "${key}" must be a string`);
      }
      return value;
    case "enum":
      if (typeof value !== "string" || !(spec.allowed as readonly string[]).includes(value)) {
        throw new LedgerSurfaceError(`field "${key}" must be one of ${JSON.stringify(spec.allowed)}`);
      }
      return value;
    case "probability": {
      if (typeof value !== "number" || Number.isNaN(value)) {
        throw new LedgerSurfaceError(`field "${key}" must be a number`);
      }
      if (value < 0 || value > 1) {
        throw new LedgerSurfaceError(`field "${key}" must lie in [0, 1]`);
      }
      return value;
    }
    case "integer": {
      if (typeof value !== "number" || !Number.isInteger(value)) {
        throw new LedgerSurfaceError(`field "${key}" must be an integer`);
      }
      if (value < (spec.minimum ?? 0)) {
        throw new LedgerSurfaceError(`field "${key}" must be >= ${spec.minimum ?? 0}`);
      }
      return value;
    }
    case "boolean":
      if (typeof value !== "boolean") {
        throw new LedgerSurfaceError(`field "${key}" must be a boolean`);
      }
      return value;
    case "killEdgeList": {
      const list = value;
      if (!Array.isArray(list) || list.some((edge) => typeof edge !== "string" || edge === "")) {
        throw new LedgerSurfaceError('field "kill_edges" must be a list of non-empty claim ids');
      }
      if (new Set(list as string[]).size !== list.length) {
        throw new LedgerSurfaceError('field "kill_edges" must not contain duplicates');
      }
      if (list.includes(all.claim_id as string)) {
        throw new LedgerSurfaceError('field "kill_edges" must not include the claim itself');
      }
      return list;
    }
    case "stringList":
      if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
        throw new LedgerSurfaceError(`field "${key}" must be a list of strings`);
      }
      return value;
    case "mapping":
      if (!isMapping(value) || (key === "preregistration" && Object.keys(value).length === 0)) {
        throw new LedgerSurfaceError(
          key === "preregistration"
            ? 'field "preregistration" must be a mapping (registered before execution)'
            : `field "${key}" must be a mapping`,
        );
      }
      return value;
    case "optionalMapping":
      if (value === null) {
        return null;
      }
      if (!isMapping(value)) {
        throw new LedgerSurfaceError(`field "${key}" must be a mapping or null`);
      }
      return value;
    case "mappingList":
      if (!Array.isArray(value) || value.some((item) => !isMapping(item))) {
        throw new LedgerSurfaceError(`field "${key}" must be a list of mappings`);
      }
      return value;
    case "optionalNonNegativeNumber": {
      if (value === null) {
        return null;
      }
      if (typeof value !== "number" || Number.isNaN(value) || value < 0) {
        throw new LedgerSurfaceError(`field "${key}" must be a non-negative number or null`);
      }
      return value;
    }
  }
}

/** Validate one surface payload; returns the normalized, key-complete record. */
export function validateSurfacePayload(table: string, payload: unknown): Payload {
  const spec = SURFACE_SPECS[table];
  if (!spec) {
    throw new LedgerSurfaceError(`unknown ledger table: ${table}`);
  }
  if (!isMapping(payload)) {
    throw new LedgerSurfaceError("payload must be a mapping");
  }
  const out: Payload = {};
  for (const [key, fieldSpec] of Object.entries(spec.fields)) {
    out[key] = validateField(payload, key, fieldSpec, table, payload);
  }
  for (const key of Object.keys(payload)) {
    if (!(key in spec.fields)) {
      throw new LedgerSurfaceError(`${table} has unexpected keys: ${JSON.stringify([key])}`);
    }
  }
  return out;
}

export { LedgerSurfaceError };
