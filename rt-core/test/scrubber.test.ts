import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, afterEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { TimelineScrubber } from "../src/canvas/scrubber.js";

let workspace: string;
let ledger: LedgerStore;
const scrubbers: TimelineScrubber[] = [];

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-scrub-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
});

afterEach(async () => {
  for (const scrubber of scrubbers.splice(0)) {
    await scrubber.close();
  }
});

function makeScrubber(name: string): TimelineScrubber {
  const scrubber = new TimelineScrubber(ledger, join(workspace, name));
  scrubbers.push(scrubber);
  return scrubber;
}

function seedResearch(taskId: string): void {
  ledger.appendGraphEvent("claim.upsert", {
    claim: { id: "c1", text: "2C4G suffices", weight: "make_or_break", posterior: 0.5, source: "research", verify_tier: "multi-source" },
  });
  ledger.appendGraphEvent("claim.upsert", {
    claim: { id: "c2", text: "p95 acceptable", weight: "important", posterior: 0.7, source: "research", verify_tier: "multi-source" },
  });
  ledger.appendGraphEvent("provider.action", {
    id: `pa-${taskId}`,
    provider: "anysearch",
    action: "search",
    target: taskId,
    outcome: "ok",
    result_count: 3,
  });
  ledger.appendGraphEvent("claim.upsert", {
    claim: { id: "c1", text: "2C4G suffices", weight: "make_or_break", posterior: 0.92, source: "research", verify_tier: "multi-source" },
  });
}

describe("timeline scrubber (issue #572)", () => {
  it("replays the canvas at any historical beat: projection(t) is pure over events <= t", async () => {
    seedResearch("t1");
    const scrubber = makeScrubber("replay.db");

    expect(scrubber.beatCount()).toBe(4);
    const early = await scrubber.projectionAt(2);
    expect(early.snapshot.Claim && Object.keys(early.snapshot.Claim)).toEqual(["c1", "c2"]);
    expect(early.console).toHaveLength(2);

    // the posterior update at beat 4 is invisible at t=2 and visible at t=4
    const claimsAt2 = early.snapshot.Claim as Record<string, Record<string, unknown>>;
    expect(claimsAt2.c1?.posterior).toBe(0.5);
    const full = await scrubber.projectionAt(4);
    const claimsAt4 = full.snapshot.Claim as Record<string, Record<string, unknown>>;
    expect(claimsAt4.c1?.posterior).toBe(0.92);
    expect(full.console).toHaveLength(4);
  });

  it("deterministic: the same beat projects identically across repeated scrubs and fresh stores", async () => {
    seedResearch("t1");
    const scrubber = makeScrubber("replay-a.db");
    const again = makeScrubber("replay-b.db");

    const first = await scrubber.projectionAt(3);
    const second = await scrubber.projectionAt(3);
    const fresh = await again.projectionAt(3);
    expect(second.snapshot).toEqual(first.snapshot); // repeated scrub
    expect(fresh.snapshot).toEqual(first.snapshot); // fresh store, same event stream
    expect(fresh.console).toEqual(first.console);
  });

  it("drags to any beat: scrubber exposes the full-run beat list with event summaries", () => {
    seedResearch("t1");
    const scrubber = makeScrubber("replay.db");
    const beats = scrubber.beats();
    expect(beats).toHaveLength(4);
    expect(beats[0]).toMatchObject({ seq: 1, event_type: "claim.upsert" });
    expect(beats[3]?.summary).toContain("c1");
  });

  it("scrubbing past the end and before the start clamp to valid ranges", async () => {
    seedResearch("t1");
    const scrubber = makeScrubber("replay.db");
    const atZero = await scrubber.projectionAt(0);
    expect(atZero.console).toHaveLength(0);
    const past = await scrubber.projectionAt(99);
    expect(past.console).toHaveLength(4);
  });
});
