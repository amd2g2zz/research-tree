/** 证据质量门测试（issue #744）：无关/空/冲突/综合失败不得完成阶段；
 * stated information gain 重查一轮；停泊后 unresolvedClaims 持久可见。
 * 黄金集取材 dogfood ISSUE-004 真实失真样本（fixtures/golden-relevance/）。
 * provider / piRunner 全注入——确定性，无网络无 pi 依赖。 */

import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";
import { ParallelDagScheduler } from "../../rt-core/src/scheduler/parallel_dag.js";
import { parseStageOutputs } from "../../rt-core/src/scheduler/stage_outcome.js";
import { LedgerStore } from "../../rt-core/src/store/ledger.js";
import { VersionStore } from "../../rt-core/src/versions/store.js";
import { BackgroundResearchRunner, type WorkerDeps } from "../src/research_worker.js";

const fixturesDir = join(import.meta.dirname, "fixtures/golden-relevance");

interface GoldenFixture {
  case: string;
  query: string;
  claims: string[];
  sources: Array<{ title: string; url?: string; snippet?: string }>;
  golden: { labels: string[]; sufficiency: string };
}

const fixtures = readdirSync(fixturesDir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(readFileSync(join(fixturesDir, f), "utf8")) as GoldenFixture);
const fixtureByCase = new Map(fixtures.map((f) => [f.case, f]));

let ledger: LedgerStore;
let versions: VersionStore;
let lines: string[];
let searchedQueries: string[];
let providerSources: GoldenFixture["sources"];
let piShouldFail: boolean;
let piResponse: string;
let piCalls: string[];

function stageStatus(stageId: string): string {
  const row = ledger.connection.prepare("SELECT status FROM parallel_stages WHERE stage_id = ?").get(stageId) as
    | { status: string }
    | undefined;
  return row?.status ?? "unknown";
}

function outcomeOf(stageId: string): ReturnType<typeof parseStageOutputs> {
  const row = ledger.connection.prepare("SELECT outputs FROM parallel_stages WHERE stage_id = ?").get(stageId) as
    | { outputs: string }
    | undefined;
  return parseStageOutputs(row?.outputs ?? "");
}

/** 医院试点任务的阶段（claim 指向真实命题文本） */
function registerHospitalStage(taskId: string): void {
  const sched = new ParallelDagScheduler(ledger);
  sched.registerStages([
    {
      stage_id: `${taskId}/s1`,
      title: "探索｜任务背景",
      status: "pending",
      claim_ids: ["c1"],
      depends_on: [],
      assigned_worker_class: "retrieval",
      retries: 0,
      max_retries: 2,
      outputs: [],
    },
  ]);
  versions.openDraft(taskId, {
    snapshot: {
      elements: {},
      claims: [
        { id: "c1", text: "小型医院 AI 病历摘要试点需要一份风险报告", posterior: 0.5 },
      ],
      evidence_refs: [],
      report: {},
      deleted_nodes: [],
    },
    baseV: null,
  });
}

function makeDeps(overrides: Partial<WorkerDeps> = {}): WorkerDeps {
  return {
    ledger,
    versions,
    provider: () =>
      ({
        async search({ query }: { query: string }) {
          searchedQueries.push(query);
          return providerSources;
        },
      }) as DataSourceProvider,
    piCommand: () => process.execPath,
    piRunner: (_command, prompt) => {
      piCalls.push(prompt);
      if (piShouldFail) return Promise.reject(new Error("pi down"));
      return Promise.resolve(piResponse);
    },
    broadcast: (line) => lines.push(line),
    maxConcurrent: 3,
    ...overrides,
  };
}

beforeEach(() => {
  const workspace = mkdtempSync(join(tmpdir(), "rt-gates-"));
  ledger = new LedgerStore(workspace);
  ledger.initialize();
  versions = new VersionStore(ledger);
  lines = [];
  searchedQueries = [];
  piCalls = [];
  piShouldFail = false;
  providerSources = fixtureByCase.get("relevant-hospital")!.sources;
  piResponse = JSON.stringify({
    findings: "综合发现：试点有明确风险清单与人工复核要求",
    sufficiency: "sufficient",
    sourceVerdicts: [{ index: 1, verdict: "relevant", basis: "直接回答试点风险问题" }],
  });
});

describe("充分性门（issue #744：无关/空/冲突/综合失败 ≠ 完成）", () => {
  it("无关源（游戏/太空 vs 医院）不得完成——stated gain 重查一轮后停泊", async () => {
    registerHospitalStage("tA");
    providerSources = fixtureByCase.get("dogfood-issue-004-irrelevant")!.sources;
    // 固定模拟模型只输出 findings（dogfood ISSUE-004 的旧输出形态）
    piResponse = JSON.stringify({ findings: "资料不足，不能得出真实结论" });
    const runner = new BackgroundResearchRunner(makeDeps());
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tA/s1")).toBe("parked");
    const outcome = outcomeOf("tA/s1");
    expect(outcome.sufficiency).toBe("insufficient");
    expect(outcome.stopReason).toBe("all-sources-irrelevant");
    expect(outcome.unresolvedClaims.some((c) => c.includes("风险报告"))).toBe(true);
    // stated information gain：重查的检索词携带未决缺口（≠ 原查询）
    expect(searchedQueries.length).toBeGreaterThanOrEqual(2);
    expect(searchedQueries[1]).not.toBe(searchedQueries[0]);
    expect(lines.some((l) => l.includes("信息增益"))).toBe(true);
    // 检索结果保留（诚实降级底座不丢数据）
    expect(outcome.sources.length).toBe(5);
  });

  it("空结果不完成——停泊 + 显式缺口（不烧综合调用）", async () => {
    registerHospitalStage("tB");
    providerSources = [];
    const runner = new BackgroundResearchRunner(makeDeps());
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tB/s1")).toBe("parked");
    const outcome = outcomeOf("tB/s1");
    expect(outcome.sufficiency).toBe("insufficient");
    expect(outcome.stopReason).toBe("empty-results");
    expect(piCalls).toHaveLength(0);
  });

  it("冲突源不完成——conflict 入 unresolvedClaims", async () => {
    registerHospitalStage("tC");
    providerSources = fixtureByCase.get("conflicted")!.sources;
    piResponse = JSON.stringify({
      findings: "来源结论冲突：一份报告零不良事件，另一份发现漏报过敏记录",
      sufficiency: "conflicted",
      unresolvedClaims: ["自动摘要能否安全替代人工初稿"],
    });
    const runner = new BackgroundResearchRunner(makeDeps());
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tC/s1")).toBe("parked");
    const outcome = outcomeOf("tC/s1");
    expect(outcome.sufficiency).toBe("conflicted");
    expect(outcome.stopReason).toBe("model-conflicted");
    expect(outcome.unresolvedClaims).toContain("自动摘要能否安全替代人工初稿");
  });

  it("充分证据（相关来源 + 模型自评充分）→ completeStage 正常完成", async () => {
    registerHospitalStage("tD");
    const runner = new BackgroundResearchRunner(makeDeps());
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tD/s1")).toBe("complete");
    const outcome = outcomeOf("tD/s1");
    expect(outcome.sufficiency).toBe("sufficient");
    expect(outcome.execution).toBe("executed");
    expect(outcome.findings[0]?.text).toContain("综合发现");
    expect(outcome.relevance[0]?.verdict).toBe("relevant");
    expect(outcome.relevance[0]?.basis).toContain("试点风险");
  });

  it("综合失败 ≠ 完成——重查仍失败后停泊，检索结果保留", async () => {
    registerHospitalStage("tE");
    piShouldFail = true;
    const runner = new BackgroundResearchRunner(makeDeps());
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tE/s1")).toBe("parked");
    const outcome = outcomeOf("tE/s1");
    expect(outcome.sufficiency).toBe("insufficient");
    expect(outcome.stopReason).toBe("synthesis-unavailable");
    expect(outcome.sources.length).toBe(3);
  });
});

describe("无进展停（issue #744：机械停条件）", () => {
  function registerDupQueryTask(taskId: string): void {
    const sched = new ParallelDagScheduler(ledger);
    const title = "verify: 竞品价格监控工具的付费意愿";
    sched.registerStages([
      {
        stage_id: `${taskId}/s1`,
        title,
        status: "pending",
        claim_ids: ["c1"],
        depends_on: [],
        assigned_worker_class: "retrieval",
        retries: 0,
        max_retries: 2,
        outputs: [],
      },
      {
        stage_id: `${taskId}/s2`,
        title, // 与 s1 同检索词——仲裁产物重复查询的机械形态
        status: "pending",
        claim_ids: ["c2"],
        depends_on: [`${taskId}/s1`],
        assigned_worker_class: "retrieval",
        retries: 0,
        max_retries: 2,
        outputs: [],
      },
    ]);
    versions.openDraft(taskId, {
      snapshot: {
        elements: {},
        claims: [
          { id: "c1", text: "竞品价格监控工具的付费意愿", posterior: 0.5 },
          { id: "c2", text: "每周自动汇总三个竞品价格变化", posterior: 0.5 },
        ],
        evidence_refs: [],
        report: {},
        deleted_nodes: [],
      },
      baseV: null,
    });
  }

  it("同任务重复查询：不再付费检索，直接停泊（stopReason=no-progress-duplicate-query）", async () => {
    registerDupQueryTask("tN1");
    const runner = new BackgroundResearchRunner(makeDeps());
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tN1/s1")).toBe("complete");
    expect(stageStatus("tN1/s2")).toBe("parked");
    // 机械性：整个任务对同一查询只付费检索一次
    expect(searchedQueries).toHaveLength(1);
    const outcome = outcomeOf("tN1/s2");
    expect(outcome.stopReason).toBe("no-progress-duplicate-query");
    expect(outcome.sufficiency).toBe("insufficient");
    expect(lines.some((l) => l.includes("重复检索"))).toBe(true);
  });

  it("连续近重复发现：任务级无进展旗标 → 仲裁员停止生长、图诚实闭合", async () => {
    // s1 重查一轮后停泊（两次相同发现），s2 独立完成（第三次相同发现）
    // → 低新颖度连续 2 次 → 旗标 → arbiterWave 拒绝生长
    const same = JSON.stringify({
      findings: "完全相同的发现文本：来源都在重复同一段内容",
      relevance: 0.9,
      coverage: 0.9,
      sufficiency: "sufficient",
      sourceVerdicts: [{ index: 1, verdict: "relevant", basis: "相关" }],
      unresolvedClaims: [],
    });
    const sched = new ParallelDagScheduler(ledger);
    sched.registerStages([
      {
        stage_id: "tN2/s1",
        title: "verify: 命题甲的独立证据",
        status: "pending",
        claim_ids: [],
        depends_on: [],
        assigned_worker_class: "retrieval",
        retries: 0,
        max_retries: 2,
        outputs: [],
      },
      {
        stage_id: "tN2/s2",
        title: "verify: 命题乙的独立证据",
        status: "pending",
        claim_ids: [],
        depends_on: [],
        assigned_worker_class: "retrieval",
        retries: 0,
        max_retries: 2,
        outputs: [],
      },
    ]);
    versions.openDraft("tN2", {
      snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] },
      baseV: null,
    });
    const runner = new BackgroundResearchRunner(
      makeDeps({
        maxConcurrent: 1, // 串行：s1 两轮 → s2 一轮，fake 序列确定
        piRunner: (_c, _p) => {
          piCalls.push(_p);
          // s1 两轮均 insufficient（重查后仍不足 → 停泊），s2 sufficient——
          // 三次调用发现完全相同：低新颖度连续 2 次 → 无进展旗标
          const calls = piCalls.length;
          if (calls <= 2) {
            return Promise.resolve(
              JSON.stringify({
                findings: "完全相同的发现文本：来源都在重复同一段内容",
                sufficiency: "insufficient",
                unresolvedClaims: ["需要独立来源"],
              }),
            );
          }
          return Promise.resolve(same);
        },
      }),
    );
    await runner.pumpOnce();
    await runner.waitForIdle();
    expect(stageStatus("tN2/s1")).toBe("parked"); // 重查后仍 insufficient
    await runner.pumpOnce(); // 第二泵：s2 派发执行 → 无进展旗标 → 仲裁拒绝生长
    await runner.waitForIdle();
    expect(stageStatus("tN2/s2")).toBe("complete");
    // 图未完成且无可派发 → 仲裁 wave——无进展旗标拒绝生长
    const grown = ledger.connection
      .prepare("SELECT COUNT(*) AS n FROM parallel_stages WHERE title LIKE '深挖｜%' OR title LIKE '分析｜%' OR title LIKE '验证｜%'")
      .get() as { n: number };
    expect(grown.n).toBe(0);
    expect(lines.some((l) => l.includes("无进展"))).toBe(true);
  });
});
