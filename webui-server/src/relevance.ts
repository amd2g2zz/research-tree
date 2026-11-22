/** 来源相关性启发式与充分性门（issue #744：无关源不得完成研究阶段）。

四态分离（docs/evaluation/2026-11-19 三处失真分析）："检索执行成功、来源相关、
证据充分、得到可用发现"是四个各有用途的事实——本模块提供其中两态的机械判定：

- `classifySourceRelevance`：查询/命题 × 来源的 bigram 重叠打分（纯函数、零
  调用成本、确定性可测）。中文无分词可用，二元字符组沿用 worker 的
  maxJaccard 既有模式。逐来源 verdict 携带 basis（可解释性要求）。
- `gateSufficiency`：充分性门——机械信号（空结果/全不相关/综合不可用）与
  模型结构化自评（conflicted/insufficient/sufficient）的合取，fail-closed：
  无正向相关证据或模型沉默时一律 insufficient，绝不静默 sufficient。

E2 黄金集实验数据（择优依据）见 openspec/changes/add-evidence-quality-gates/
design.md。启发式常开为基线；综合调用在同一 JSON 里输出逐来源 verdict（无
新增付费调用）时覆盖启发式——budget/stop 守卫天然满足。 */

export type RelevanceVerdict = "relevant" | "irrelevant" | "uncertain";
export type Sufficiency = "sufficient" | "insufficient" | "conflicted";

export interface SourceRelevanceVerdict {
  /** 稳定引用（s1、s2…）——StageOutcome.findings 的 evidenceIds 指向它 */
  sourceRef: string;
  verdict: RelevanceVerdict;
  /** 一句话依据（可解释性；#697 溯源律先例——无依据不判） */
  basis: string;
  /** 启发式原始分（0~1，观测用；模型 verdict 覆盖时保留启发式分） */
  score: number;
}

export interface RelevanceThresholds {
  relevant: number;
  uncertain: number;
}

/** 阈值由 E2 黄金集校准（design.md 数据表）：relevant ≥0.15 且命中字符组
 * ≥2（union 去重）、uncertain ≥0.05，低于即 irrelevant。 */
export const DEFAULT_RELEVANCE_THRESHOLDS: RelevanceThresholds = {
  relevant: 0.15,
  uncertain: 0.05,
};

/** 二元字符组（无嵌入的机械重叠信号；沿用 maxJaccard 的既有模式）。
 * 虚词字符组（含 的/是/了 等单虚词字的组）剔除——"的任务"这类跨虚词滑窗
 * 会用相邻重叠组击穿命中数守卫（E2 黄金集实测假阳性根因）。 */
const STOPWORD_CHARS = new Set([..."的了是在和与对为及或等之其这那由从被按据向于把个也很就很"]);

function bigrams(text: string): Set<string> {
  const s = text
    .toLowerCase()
    .replace(/[\s\p{P}\p{S}]+/gu, "");
  const out = new Set<string>();
  for (let i = 0; i + 2 <= s.length; i += 1) {
    const gram = s.slice(i, i + 2);
    if (STOPWORD_CHARS.has(gram[0]!) || STOPWORD_CHARS.has(gram[1]!)) continue;
    out.add(gram);
  }
  return out;
}

export interface RelevanceReference {
  /** 阶段检索词 */
  query: string;
  /** 阶段命题文本（claimTexts）——语义主体，检索词常是泛称（"任务背景"） */
  claims: string[];
}

export interface SourceLike {
  title: string;
  url?: string;
  snippet?: string;
}

/** 启发式逐来源相关性判定：score = max(逐参照部分的重叠比)——检索词与每条
 * 命题各自成参照（短泛称检索词单独成部会被"背景音"类假阳性利用，故 relevant
 * 另要求全部命中字符组 ≥2——单个泛称字符组命中只能给 uncertain）。 */
export function classifySourceRelevance(
  reference: RelevanceReference,
  sources: SourceLike[],
  thresholds: RelevanceThresholds = DEFAULT_RELEVANCE_THRESHOLDS,
): SourceRelevanceVerdict[] {
  const parts = [reference.query, ...reference.claims].filter((p) => p.trim() !== "");
  return sources.map((source, i) => {
    const src = bigrams(`${source.title} ${source.snippet ?? ""}`);
    let score = 0;
    const matched = new Set<string>();
    for (const part of parts) {
      const ref = bigrams(part);
      if (ref.size === 0) continue;
      let inter = 0;
      for (const g of ref) {
        if (src.has(g)) {
          inter += 1;
          matched.add(g); // union 去重：query 与 claim 共享字符组不得重复计数
        }
      }
      score = Math.max(score, inter / ref.size);
    }
    const totalInter = matched.size;
    const verdict: RelevanceVerdict =
      score >= thresholds.relevant && totalInter >= 2
        ? "relevant"
        : score >= thresholds.uncertain && totalInter >= 1
          ? "uncertain"
          : "irrelevant";
    return {
      sourceRef: `s${i + 1}`,
      verdict,
      basis:
        verdict === "relevant"
          ? `与命题字符组重叠 ${score.toFixed(2)}（≥${thresholds.relevant}，命中 ${totalInter} 组）`
          : verdict === "uncertain"
            ? `与命题字符组重叠 ${score.toFixed(2)}（不足以判定直接相关）`
            : `与命题字符组重叠 ${score.toFixed(2)}（<${thresholds.uncertain}）`,
      score,
    };
  });
}

export interface ModelVerdictInput {
  index: number;
  verdict: RelevanceVerdict;
  basis: string;
}

export interface SufficiencyGateInput {
  sources: SourceLike[];
  /** 机械启发式判定（常开基线） */
  heuristicVerdicts: SourceRelevanceVerdict[];
  /** 综合是否可用（pi 在场且本次综合成功解析） */
  modelAvailable: boolean;
  /** 综合结构化自评（旧输出形态无此字段 → undefined） */
  modelSufficiency?: Sufficiency;
  /** 综合逐来源 verdict（新输出形态才提供；覆盖启发式，携带 basis） */
  modelVerdicts?: ModelVerdictInput[];
  /** 综合自陈的未决点（conflicted/insufficient 时的具体缺口） */
  modelUnresolvedClaims?: string[];
  /** 阶段命题文本——未决主张要落到这些 claim 上（issue 验收原文） */
  claims: string[];
}

export interface SufficiencyGateResult {
  sufficiency: Sufficiency;
  /** 显式未决：命题文本 + 缺口原因——insufficient/conflicted 必非空 */
  unresolvedClaims: string[];
  /** stated information gain（issue 验收原文：避免无 stated gain 的重查）——
   * 紧凑一句话，重查检索词与 broadcast 都用它。 */
  informationGain: string;
  /** 合并后的逐来源判定（模型 verdict 覆盖启发式时以覆盖后为准）——落
   * StageOutcome.relevance */
  verdicts: SourceRelevanceVerdict[];
  /** 机械停条件标识（TDD 矩阵逐条断言的对象） */
  stopReason?:
    | "empty-results"
    | "all-sources-irrelevant"
    | "synthesis-unavailable"
    | "model-insufficient"
    | "model-conflicted"
    | "sufficient-without-relevant-source";
}

/** 充分性门（fail-closed）：
 * - 空结果 / 综合不可用 / 模型沉默 → insufficient；
 * - 机械底线：启发式判全部不相关且模型未给出逐来源 verdict（无 basis 的
 *   溯源）⇒ insufficient——模型自评不得翻转此底线（#697 先例：无溯源即剪枝）；
 * - 模型提供逐来源 verdict（带 basis）时覆盖启发式判定，机械底线让位给
 *   可解释判定；sufficient 仍要求 ≥1 条 relevant。 */
export function gateSufficiency(input: SufficiencyGateInput): SufficiencyGateResult {
  const claimTexts = input.claims.length > 0 ? input.claims : ["（无命题文本）"];
  if (input.sources.length === 0) {
    return {
      sufficiency: "insufficient",
      unresolvedClaims: [...claimTexts, "检索无结果：未获得任何来源"],
      informationGain: "任何与命题相关的来源",
      verdicts: [],
      stopReason: "empty-results",
    };
  }
  const heuristicRelevantCount = input.heuristicVerdicts.filter((v) => v.verdict === "relevant").length;
  const merged: SourceRelevanceVerdict[] =
    input.modelVerdicts !== undefined && input.modelVerdicts.length > 0
      ? input.heuristicVerdicts.map((h) => {
          const m = input.modelVerdicts!.find((mv) => mv.index === Number(h.sourceRef.slice(1)));
          return m !== undefined
            ? { ...h, verdict: m.verdict, basis: m.basis !== "" ? m.basis : h.basis }
            : h;
        })
      : input.heuristicVerdicts;
  const relevantCount = merged.filter((v) => v.verdict === "relevant").length;
  // 机械底线：启发式无任何 positively-relevant 来源且模型未给出带 basis 的
  // 逐来源判定 ⇒ insufficient（模型自评不得翻转；#697 先例：无溯源即剪枝）
  if (heuristicRelevantCount === 0 && (input.modelVerdicts === undefined || input.modelVerdicts.length === 0)) {
    const titles = input.sources.map((s) => `《${s.title.slice(0, 24)}》`).join("、");
    return {
      sufficiency: "insufficient",
      unresolvedClaims: [...claimTexts, `未检出与命题直接相关的来源（${titles}）——需要与命题直接相关的来源`],
      informationGain: "与命题直接相关的来源",
      verdicts: merged,
      stopReason: "all-sources-irrelevant",
    };
  }
  if (!input.modelAvailable) {
    return {
      sufficiency: "insufficient",
      unresolvedClaims: [...claimTexts, "综合模型不可用——无法从来源形成可用发现"],
      informationGain: "综合模型可用后从来源形成可用发现",
      verdicts: merged,
      stopReason: "synthesis-unavailable",
    };
  }
  if (input.modelSufficiency === "conflicted") {
    return {
      sufficiency: "conflicted",
      unresolvedClaims: [
        ...claimTexts,
        ...(input.modelUnresolvedClaims ?? []),
        "来源结论冲突——需要裁决性证据",
      ],
      informationGain: "裁决来源冲突的独立证据",
      verdicts: merged,
      stopReason: "model-conflicted",
    };
  }
  if (input.modelSufficiency === "insufficient") {
    return {
      sufficiency: "insufficient",
      unresolvedClaims: [...claimTexts, ...(input.modelUnresolvedClaims ?? ["综合自评证据不足"])],
      informationGain: input.modelUnresolvedClaims?.[0] ?? "补足综合自评指出的证据缺口",
      verdicts: merged,
      stopReason: "model-insufficient",
    };
  }
  if (input.modelSufficiency === "sufficient" && relevantCount >= 1) {
    return { sufficiency: "sufficient", unresolvedClaims: [], informationGain: "", verdicts: merged };
  }
  if (input.modelSufficiency === "sufficient") {
    return {
      sufficiency: "insufficient",
      unresolvedClaims: [...claimTexts, "综合自评充分但未检出直接相关来源——fail-closed 拒绝完成"],
      informationGain: "与命题直接相关的来源",
      verdicts: merged,
      stopReason: "sufficient-without-relevant-source",
    };
  }
  return {
    sufficiency: "insufficient",
    unresolvedClaims: [...claimTexts, "综合未给出充分性自评（旧输出形态）——不能证明充分"],
    informationGain: "综合给出充分性自评与逐来源依据",
    verdicts: merged,
    stopReason: "model-insufficient",
  };
}
