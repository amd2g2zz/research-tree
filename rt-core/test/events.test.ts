import { describe, expect, it } from "vitest";

import {
  GRAPH_EVENT_TYPES,
  GraphEventError,
  validateGraphEvent,
} from "../src/events/vocabulary.js";

const CLAIM = {
  id: "c1",
  text: "rt works offline",
  source: "user",
  weight: "make_or_break",
  posterior: 0.5,
  verify_tier: "multi-source",
};

const MINIMAL_PAYLOADS: Record<string, Record<string, unknown>> = {
  "claim.upsert": { claim: { ...CLAIM } },
  "claim.kill_edge": { claim_id: "c1", kill_target_id: "c2" },
  "stage.upsert": { stage: { id: "s1", title: "cluster", status: "open" } },
  "stage.depends_on": { stage_id: "s2", depends_on_id: "s1" },
  "stage.contains": { stage_id: "s1", claim_id: "c1" },
  "evidence.upsert": { evidence: { id: "e1", digest: "a".repeat(64), origin: "origin.py" } },
  "evidence.attach": { evidence_id: "e1", claim_id: "c1" },
  "artifact.upsert": { artifact: { id: "a1", kind: "finding-pack", digest: "b".repeat(64) } },
  "artifact.link": { artifact_id: "a1", claim_id: "c1" },
  "version.commit": {
    version: { id: "t1:0", task_id: "t1", v: 0, commit_hash: "c".repeat(64), verdict: "GO", summary: "first commit" },
  },
  "fork.edge": { child_version_id: "t2:0", parent_version_id: "t1:0" },
};

describe("graph event vocabulary", () => {
  it.each([...GRAPH_EVENT_TYPES])("accepts a minimal payload for %s", (eventType) => {
    const normalized = validateGraphEvent(eventType, MINIMAL_PAYLOADS[eventType]);
    expect(normalized).toBeTypeOf("object");
  });

  it("rejects unknown event types", () => {
    expect(() => validateGraphEvent("claim.teleport", { claim_id: "c1" })).toThrow(GraphEventError);
    expect(() => validateGraphEvent("claim.teleport", { claim_id: "c1" })).toThrow(/unknown graph event type/);
  });

  it("rejects non-mapping payloads", () => {
    expect(() => validateGraphEvent("claim.kill_edge", ["c1", "c2"])).toThrow(/payload must be a mapping/);
  });

  it("fills the stale default on claim.upsert", () => {
    const normalized = validateGraphEvent("claim.upsert", { claim: { ...CLAIM } }) as {
      claim: { stale: boolean };
    };
    expect(normalized.claim.stale).toBe(false);
  });

  it("rejects posterior outside [0, 1]", () => {
    const bad = { claim: { ...CLAIM, posterior: 1.5 } };
    expect(() => validateGraphEvent("claim.upsert", bad)).toThrow(/posterior/);
  });

  it("rejects unknown weight/source/verify_tier", () => {
    expect(() => validateGraphEvent("claim.upsert", { claim: { ...CLAIM, weight: "load_bearing" } })).toThrow(/weight/);
    expect(() => validateGraphEvent("claim.upsert", { claim: { ...CLAIM, source: "vibes" } })).toThrow(/source/);
    expect(() => validateGraphEvent("claim.upsert", { claim: { ...CLAIM, verify_tier: "vibes" } })).toThrow(
      /verify_tier/,
    );
  });

  it("rejects unknown verdict and negative v on version.commit", () => {
    const version = { ...(MINIMAL_PAYLOADS["version.commit"] as any).version };
    expect(() => validateGraphEvent("version.commit", { version: { ...version, verdict: "MAYBE" } })).toThrow(
      /verdict/,
    );
    expect(() => validateGraphEvent("version.commit", { version: { ...version, v: -1 } })).toThrow(/"v"/);
  });

  it("requires distinct fork ids", () => {
    expect(() => validateGraphEvent("fork.edge", { child_version_id: "t1:0", parent_version_id: "t1:0" })).toThrow(
      /distinct/,
    );
  });

  it("names missing required ids", () => {
    expect(() => validateGraphEvent("claim.kill_edge", { kill_target_id: "c2" })).toThrow(/claim_id/);
  });

  it("rejects unexpected payload keys", () => {
    expect(() =>
      validateGraphEvent("claim.kill_edge", { claim_id: "c1", kill_target_id: "c2", why: "nope" }),
    ).toThrow(/unexpected keys/);
  });
});
