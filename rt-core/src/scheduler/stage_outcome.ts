/** StageOutcome：研究阶段产出的四态结构化记录（issue #744）。

"检索执行成功、来源相关、证据充分、得到可用发现"是四个各有用途的事实
（docs/evaluation/2026-11-19 失真分析 3：保存成功 ≠ 证据足够 ≠ 问题已回答）。
#744 之前 parallel_stages.outputs 存裸 artifact JSON（双重编码数组），四态
被压缩成一个 complete；本模块定义结构化形态与三形态读取归一化：

- StageOutcome（schema 2）：completeStage 的新写形态；
- legacy：#744 之前的 `["<artifact JSON>"]` 裸行——解析时显式标注
  execution=executed / sufficiency=unknown，原 artifact 整体保留在 legacy
  字段（不丢数据）；
- 损坏行 fail-closed：不崩溃、unknown、解析失败显式入 unresolvedClaims。

迁移（ledger v12）用 migrateLegacyStageOutputs：与解析同一套逻辑（单一
事实来源），只改写 legacy 形态的行，幂等。 */

import type { Database } from "better-sqlite3";

export type StageExecution = "executed" | "failed";
/** unknown 只出现在迁移/损坏行——四态分离前无法证明任何一态，显式标注。 */
export type StageSufficiency = "sufficient" | "insufficient" | "conflicted" | "unknown";

export interface StageSourceVerdict {
  /** 稳定来源引用（s1、s2…）——findings[].evidenceIds 指向它 */
  sourceRef: string;
  verdict: "relevant" | "irrelevant" | "uncertain";
  /** 一句话依据（可解释性；#697 溯源律先例——无依据不判） */
  basis: string;
}

export interface StageFinding {
  findingId: string;
  /** 来源引用（s1…）；#746 EvidenceRecord 落地后升级为 evidenceId */
  evidenceIds: string[];
  text: string;
}

export interface StageBranchCoverage {
  branch: string;
  status: "answered" | "gap";
}

export interface StageOutcome {
  schema: 2;
  execution: StageExecution;
  sufficiency: StageSufficiency;
  relevance: StageSourceVerdict[];
  /** 显式未决主张——insufficient/conflicted 必非空 */
  unresolvedClaims: string[];
  findings: StageFinding[];
  sources: Array<{ title: string; url?: string; snippet?: string }>;
  /** 检索词（stated information gain 重查链路可观测） */
  query?: string;
  /** stated information gain——insufficient 时重查检索词携带的增益声明 */
  informationGain?: string;
  /** 汇总节点专用：逐分支覆盖（answered/gap） */
  coverage?: StageBranchCoverage[];
  /** 机械停条件标识（TDD 矩阵逐条断言的对象） */
  stopReason?: string;
  /** 迁移保留：#744 之前的原 artifact（不丢数据） */
  legacy?: unknown;
}

interface LegacyArtifact {
  title?: unknown;
  query?: unknown;
  findings?: unknown;
  sources?: unknown;
  completed_at?: unknown;
}

/** fail-closed 构造：unknown 态显式标注（不发明 verdict）。 */
function unknownOutcome(reason: string, extra: Partial<StageOutcome> = {}): StageOutcome {
  return {
    schema: 2,
    execution: "executed",
    sufficiency: "unknown",
    relevance: [],
    unresolvedClaims: [reason],
    findings: [],
    sources: [],
    ...extra,
  };
}

/** outputs 列读取归一化：StageOutcome 原样返回（缺失数组补空）、legacy
 * 显式标注迁移、损坏 fail-closed。画布 projection 与 worker 读取统一走这里。 */
export function parseStageOutputs(raw: string | null | undefined): StageOutcome {
  if (raw === null || raw === undefined || raw.trim() === "") {
    return unknownOutcome("产出为空——阶段未产出可解析记录");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return unknownOutcome("产出解析失败——outputs 不是合法 JSON");
  }
  if (Array.isArray(parsed)) {
    if (parsed.length === 0) {
      return unknownOutcome("产出为空——阶段未产出可解析记录");
    }
    let artifact: LegacyArtifact | null = null;
    try {
      const first = JSON.parse(String(parsed[0] ?? "")) as unknown;
      if (first !== null && typeof first === "object") artifact = first as LegacyArtifact;
    } catch {
      artifact = null;
    }
    if (artifact === null) {
      return unknownOutcome("产出解析失败——legacy 行无法还原 artifact");
    }
    const findingsText = typeof artifact.findings === "string" ? artifact.findings : "";
    const sources = Array.isArray(artifact.sources)
      ? (artifact.sources as StageOutcome["sources"])
      : [];
    return {
      schema: 2,
      execution: "executed",
      sufficiency: "unknown",
      relevance: [],
      unresolvedClaims: [],
      findings: findingsText !== "" ? [{ findingId: "legacy", evidenceIds: [], text: findingsText }] : [],
      sources,
      query: typeof artifact.query === "string" ? artifact.query : undefined,
      legacy: artifact,
    };
  }
  if (parsed !== null && typeof parsed === "object" && (parsed as { schema?: unknown }).schema === 2) {
    const outcome = parsed as StageOutcome;
    return {
      ...outcome,
      relevance: Array.isArray(outcome.relevance) ? outcome.relevance : [],
      unresolvedClaims: Array.isArray(outcome.unresolvedClaims) ? outcome.unresolvedClaims : [],
      findings: Array.isArray(outcome.findings) ? outcome.findings : [],
      sources: Array.isArray(outcome.sources) ? outcome.sources : [],
    };
  }
  return unknownOutcome("产出解析失败——outputs 形态不可识别");
}

/** ledger migration v12：把 legacy 形态（`["<artifact>"]` 数组）重写为
 * StageOutcome（execution=executed / sufficiency=unknown 显式标注，原
 * artifact 保留在 legacy）。幂等：schema 2 行与损坏行不动（损坏行留给
 * parseStageOutputs 的 fail-closed 路径，不丢任何字节）。 */
export function migrateLegacyStageOutputs(db: Database): number {
  const rows = (
    db.prepare("SELECT stage_id, outputs FROM parallel_stages").all() as Array<{
      stage_id: string;
      outputs: string;
    }>
  ).filter((row) => isLegacyOutputsRow(row.outputs));
  const update = db.prepare("UPDATE parallel_stages SET outputs = ? WHERE stage_id = ?");
  for (const row of rows) {
    update.run(migrateOutputsValue(row.outputs), row.stage_id);
  }
  return rows.length;
}

function isLegacyOutputsRow(raw: string): boolean {
  if (raw === null || raw === undefined) return false;
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed);
  } catch {
    return false;
  }
}

/** 纯函数：legacy 行值 → StageOutcome JSON 值（迁移与测试共用）。 */
export function migrateOutputsValue(raw: string): string {
  return JSON.stringify(parseStageOutputs(raw));
}
