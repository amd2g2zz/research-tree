import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { LedgerStore } from "../src/store/ledger.js";
import { VersionStore } from "../src/versions/store.js";
import { ProjectHomeModel, ProjectHomeError } from "../src/ux/project_home.js";

let workspace: string;
let ledger: LedgerStore;
let versions: VersionStore;
let home: ProjectHomeModel;

beforeEach(() => {
  workspace = mkdtempSync(join(tmpdir(), "rt-home-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  home = new ProjectHomeModel(ledger, versions);
});

function commitOne(taskId: string, verdict = "GO") {
  versions.openDraft(taskId, {
    snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] },
    baseV: null,
  });
  return versions.freeze(taskId, { verdict, summary: `${taskId} v0` });
}

describe("project home & card wall (issue #571, P0)", () => {
  it("create lands a project card with name/description/attachment chips", () => {
    const card = home.createProject("p1", {
      name: "2C4G 部署可行性",
      description: "验证 2C4G 是否够用",
      attachments: [{ id: "att:1", kind: "xlsx", label: "压测数据.xlsx" }],
    });
    expect(card.name).toBe("2C4G 部署可行性");
    expect(card.status).toBe("active");
    expect(card.attachments).toHaveLength(1);
    expect(home.listProjects().map((p) => p.project_id)).toEqual(["p1"]);
  });

  it("vitals are empty before research and reflect live state after commits", () => {
    home.createProject("p1", { name: "n", description: "" });
    expect(home.vitals("p1")).toMatchObject({ research_lines: 0, latest: null });

    home.registerTask("p1", "t-main", "main");
    commitOne("t-main");
    const vitals = home.vitals("p1");
    expect(vitals.research_lines).toBe(1);
    expect(vitals.latest).toMatchObject({ v: 0, verdict: "GO" });
    expect(String(vitals.latest?.commit_hash)).toHaveLength(64);
    expect(vitals.elapsed_ms).toBeGreaterThanOrEqual(0);

    // a fork adds a research line without touching the main-line vitals
    home.registerTask("p1", "t-fork", "fork");
    expect(home.vitals("p1").research_lines).toBe(2);
    expect(home.vitals("p1").latest?.v).toBe(0);
  });

  it("default projection is always the main branch's latest version (A7 rule 5)", () => {
    home.createProject("p1", { name: "n", description: "" });
    home.registerTask("p1", "t-main", "main");
    commitOne("t-main", "PARK");
    versions.openDraftFromVersion("t-main", 0);
    versions.mutateDraft("t-main", (draft) => {
      draft.snapshot.claims = [{ id: "c1", text: "new claim from continued research" }];
    });
    versions.freeze("t-main", { verdict: "GO", summary: "v1" });

    const projection = home.defaultProjection("p1");
    expect(projection.v).toBe(1);
    expect(projection.verdict).toBe("GO");
    // a fork's newer commits never hijack the main-branch default
    home.registerTask("p1", "t-fork", "fork");
    commitOne("t-fork", "NO-GO");
    expect(home.defaultProjection("p1").v).toBe(1);
  });

  it("after the first commit the 查看最新报告 entry grows automatically", () => {
    home.createProject("p1", { name: "n", description: "" });
    home.registerTask("p1", "t-main", "main");
    expect(home.hasLatestReport("p1")).toBe(false);
    commitOne("t-main");
    expect(home.hasLatestReport("p1")).toBe(true);
  });

  it("a project has exactly one main line (second main rejected)", () => {
    home.createProject("p1", { name: "n", description: "" });
    home.registerTask("p1", "t-main", "main");
    expect(() => home.registerTask("p1", "t-other", "main")).toThrow(/main/);
  });

  it("archive is read-only; delete is blocked for non-archived and allowed for archived", () => {
    home.createProject("p1", { name: "n", description: "" });
    home.registerTask("p1", "t-main", "main");
    expect(() => home.deleteProject("p1")).toThrow(/archiv/); // delete blocked while active
    home.archiveProject("p1");
    expect(home.get("p1")?.status).toBe("archived");
    // archived projects are read-only: no new research lines
    expect(() => home.registerTask("p1", "t2", "fork")).toThrow(/archived/);
    home.deleteProject("p1");
    expect(home.get("p1")).toBeNull();
  });

  it("multi-project isolation: zero cross-talk between parallel projects", () => {
    home.createProject("pA", { name: "A", description: "" });
    home.createProject("pB", { name: "B", description: "" });
    home.registerTask("pA", "t-a", "main");
    commitOne("t-a", "GO");
    // B has no lines and no versions despite t-a existing in the same ledger
    expect(home.vitals("pB")).toMatchObject({ research_lines: 0, latest: null });
    // archive/delete of A never touches B
    home.archiveProject("pA");
    expect(home.get("pB")?.status).toBe("active");
    expect(home.vitals("pB").research_lines).toBe(0);
  });

  it("unknown projects throw a typed error", () => {
    expect(() => home.vitals("ghost")).toThrow(ProjectHomeError);
  });
});
