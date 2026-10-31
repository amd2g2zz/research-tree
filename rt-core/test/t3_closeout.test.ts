/** T3 closeout acceptance (issue #576): 多项目隔离 + 四态归档 + 回放确定性,
 * driven as ONE integrated scenario across the T3 modules (#571 project home,
 * #572 scrubber, #573 four-state archive, #574 version timeline).

External harness success (#575) was removed by the 2026-10-30 pi-only ruling;
the MCP exit (#553) stays as the product interface and is exercised in the
existing mcp/e2e suites — not re-tested here.
*/

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, afterEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { EngineCore } from "../src/store/engine.js";
import { ProductStateMachine } from "../src/state/machine.js";
import { ProjectHomeModel } from "../src/ux/project_home.js";
import { TimelineScrubber } from "../src/canvas/scrubber.js";
import { FourStateArchive } from "../src/versions/archive.js";
import { VersionTimeline } from "../src/versions/timeline.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let machine: ProductStateMachine;
let home: ProjectHomeModel;
let timeline: VersionTimeline;
let archive: FourStateArchive;
const scrubbers: TimelineScrubber[] = [];

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-t3close-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  machine = new ProductStateMachine(new EngineCore(ledger), versions);
  home = new ProjectHomeModel(ledger, versions);
  timeline = new VersionTimeline(ledger, versions, machine);
  archive = new FourStateArchive(ledger, versions, machine);
});

afterEach(async () => {
  for (const scrubber of scrubbers.splice(0)) {
    await scrubber.close();
  }
});

function commit(taskId: string, verdict: string, marker: string) {
  const existing = versions.draftOf(taskId);
  const snapshot = {
    elements: {},
    claims: [{ id: `c-${marker}`, text: `claim ${marker}` }],
    evidence_refs: ["sha256:" + marker.repeat(8) + "a".repeat(24)],
    report: { marker },
    deleted_nodes: [],
  };
  if (existing === null) {
    versions.openDraft(taskId, { snapshot, baseV: null });
  } else {
    versions.mutateDraft(taskId, (draft) => {
      draft.snapshot = snapshot;
    });
  }
  return versions.freeze(taskId, { verdict, summary: `${taskId} ${marker} → ${verdict}` });
}

describe("T3 closeout — integrated walk (issue #576)", () => {
  it("multi-project isolation + four-state archive + fork inheritance + deterministic replay, in one ledger", async () => {
    // ---------------------------------------------------------- two projects
    home.createProject("pA", { name: "主项目", description: "", attachments: [{ id: "att:1", kind: "xlsx", label: "data.xlsx" }] });
    home.createProject("pB", { name: "支线项目", description: "" });
    home.registerTask("pA", "tA", "main");
    home.registerTask("pB", "tB", "main");

    // project A: v0 GO → v1 NO-GO (graveyard) + fork from v0
    commit("tA", "GO", "aaaa0001");
    commit("tA", "NO-GO", "aaaa0002");
    timeline.fork("tA", 0, "tA-fork");
    home.registerTask("pA", "tA-fork", "fork"); // fork lines register in their project
    // project B: v0 PARK
    commit("tB", "PARK", "bbbb0001");

    // ------------------------------------------- multi-project isolation (#571)
    expect(home.vitals("pA").research_lines).toBe(2); // main + fork
    expect(home.vitals("pB").research_lines).toBe(1);
    expect(home.defaultProjection("pA").task_id).toBe("tA"); // fork never hijacks
    expect(home.defaultProjection("pB").task_id).toBe("tB");
    expect(home.vitals("pA").latest?.v).toBe(1);

    // ------------------------------------------ four-state archival (#573)
    expect(() => archive.archive("tA", 1, { reason: "OOM" })).toThrow(/revival/); // red line pinned
    archive.archive("tA", 0); // GO → deliverable
    archive.archive("tA", 1, { reason: "OOM postmortem", revival_conditions: ["4C8G pilot budget"] });
    expect(() => archive.archive("tB", 0, { brief: "waiting" })).toThrow(/revival/);
    archive.archive("tB", 0, { brief: "frozen brief", revival_conditions: ["budget window"] });
    // REFRAMED inheritance: a REFRAMED-committed version forks to a new task with delta report
    commit("tA-fork", "REFRAMED", "aaaa0003");
    archive.archive("tA-fork", 1, { delta_report: "the real question is memory ceiling", new_task_id: "tA-reframed" });
    expect(machine.phaseOf("tA-reframed")).toBe("chat");
    expect(versions.getVersion("tA-reframed", 0)).not.toBeNull();
    const graveyard = archive.graveyard();
    expect(graveyard.map((e) => e.task_id)).toEqual(["tA"]);
    expect(archive.list()).toHaveLength(4);

    // ------------------------------------------ graveyard revival (#573+#574)
    archive.revive("tA", 1, "tA-reborn");
    expect(archive.entry("tA", 1)?.revived_to).toBe("tA-reborn");
    expect(versions.forkChildren("tA", 1).map((c) => c.task_id)).toContain("tA-reborn");

    // ------------------------------------------ fork inheritance measured (#574)
    const forked = versions.getVersion("tA-fork", 0)!;
    expect(forked.snapshot.evidence_refs).toEqual(versions.getVersion("tA", 0)!.snapshot.evidence_refs);

    // ------------------------------------------ snapshot read-only (#574)
    const hashBefore = versions.getVersion("tA", 0)!.commit_hash;
    const snap = timeline.snapshotView("tA", 0);
    expect(snap.banner).toMatchObject({ v: 0, verdict: "GO" });
    versions.openDraftFromVersion("tA", 0);
    expect(() => versions.freeze("tA", { verdict: "GO", summary: "same" })).toThrow();
    expect(versions.getVersion("tA", 0)!.commit_hash).toBe(hashBefore);

    // ------------------------------------------ H7 telemetry live (#574)
    const telemetry = ledger
      .graphEvents()
      .filter((e) => e.event_type === "provider.action")
      .filter((e) => (e.payload as Record<string, unknown>).provider === "telemetry");
    const targets = telemetry.map((e) => String((e.payload as Record<string, unknown>).target));
    expect(targets.some((t) => t.startsWith("fork:"))).toBe(true);

    // ------------------------------------------ full-run deterministic replay (#572)
    // research activity lands as graph events (claims move during the run)
    ledger.appendGraphEvent("claim.upsert", {
      claim: { id: "cA1", text: "A claim", weight: "make_or_break", posterior: 0.55, source: "research", verify_tier: "multi-source" },
    });
    ledger.appendGraphEvent("claim.upsert", {
      claim: { id: "cA1", text: "A claim", weight: "make_or_break", posterior: 0.93, source: "research", verify_tier: "multi-source" },
    });
    const scrubber = new TimelineScrubber(ledger, join(workspace, "replay.db"));
    scrubbers.push(scrubber);
    const again = new TimelineScrubber(ledger, join(workspace, "replay2.db"));
    scrubbers.push(again);
    const beatCount = scrubber.beatCount();
    expect(beatCount).toBeGreaterThanOrEqual(6);
    const mid = await scrubber.projectionAt(Math.floor(beatCount / 2));
    const midAgain = await scrubber.projectionAt(Math.floor(beatCount / 2));
    const midFresh = await again.projectionAt(Math.floor(beatCount / 2));
    expect(midAgain.snapshot).toEqual(mid.snapshot);
    expect(midFresh.snapshot).toEqual(mid.snapshot);
    const full = await scrubber.projectionAt(beatCount);
    expect(full.console).toHaveLength(beatCount);
    // the morning canvas replays the full run from the log alone
    expect(() => ledger.verifyGraphChain()).not.toThrow();
  });

  it("delete rules hold across the integrated state: active blocked, archived allowed, isolation intact", () => {
    home.createProject("pX", { name: "X", description: "" });
    home.createProject("pY", { name: "Y", description: "" });
    home.registerTask("pX", "tX", "main");
    expect(() => home.deleteProject("pX")).toThrow(/archiv/);
    home.archiveProject("pX");
    home.deleteProject("pX");
    expect(home.get("pX")).toBeNull();
    expect(home.get("pY")?.status).toBe("active");
    expect(home.vitals("pY").research_lines).toBe(0);
  });
});
