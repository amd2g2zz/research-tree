/** Dual rendering — report narrative + 底稿, same-source projection (issue #560).

渲染是纯函数: both projections derive from ONE snapshot and can never
contradict. The report is the narrative (7 sections, docs 03 §报告与底稿);
the 底稿 is the structure rendering = downstream interface (schema v1, frozen).

Red lines carried:
- 反证章 always present (counter-evidence section);
- confidence is qualitative bands only — no fake percentages;
- PARK always carries revival conditions; 底稿 always contains
  unverified_assumptions;
- deleted nodes disclosed (产物删除 auditable).
*/

export interface RenderSnapshot {
  elements?: {
    requirements?: Array<Record<string, unknown>>;
    constraints?: Array<Record<string, unknown>>;
    background?: Array<Record<string, unknown>>;
    intents?: Array<Record<string, unknown>>;
    refusals?: Array<Record<string, unknown>>;
    difficulties?: Array<Record<string, unknown>>;
  } | Record<string, unknown> | null;
  claims?: Array<Record<string, unknown>>;
  evidence_refs?: string[];
  report?: Record<string, unknown> | null;
  deleted_nodes?: string[];
  [key: string]: unknown;
}

export interface RenderContext {
  verdict: string;
  confidence: "high" | "moderate" | "low";
}

export interface Deliverable {
  clarified_question: Record<string, unknown>;
  supported_claims: Array<{ text: string; posterior: number; verify_tier: string }>;
  unverified_assumptions: Array<{ text: string; reason: string }>;
  refuted_and_disposition: Array<{ text: string; disposition: string }>;
  capability_outline: string[];
  constraints: { hard: string[]; guessed: string[] };
  deleted_nodes_disclosed: string[];
}

const CONFIDENCE_NOTE: Record<string, string> = {
  high: "high — converging evidence across independent methods",
  moderate: "moderate — supporting evidence with open caveats",
  low: "low — thin or single-source evidence",
};

function elementList(snapshot: RenderSnapshot, key: string): Array<Record<string, unknown>> {
  const elements: unknown = snapshot.elements;
  if (elements === null || typeof elements !== "object" || Array.isArray(elements)) {
    return [];
  }
  const list = (elements as Record<string, unknown>)[key];
  return Array.isArray(list) ? (list as Array<Record<string, unknown>>) : [];
}

export function renderReport(snapshot: RenderSnapshot, ctx: { verdict: string; confidence: string }): string {
  const claims = snapshot.claims ?? [];
  const mob = claims.filter((claim) => claim.weight === "make_or_break");
  const refuted = claims.filter((claim) => Number(claim.posterior) <= 0.1);
  const requirements = elementList(snapshot, "requirements").map((r) => String(r.text));
  const refusals = elementList(snapshot, "refusals").map((r) => String(r.text));
  const deleted = snapshot.deleted_nodes ?? [];

  const sections: string[] = [];
  sections.push(`## 1. 你的想法，被这样理解了\n\n${requirements.join("；") || "(未登记)"}`);
  sections.push(
    "## 2. 我们怎么验证的\n\n"
    + "方法透明：分层验证（文献交叉 / 逻辑盲推 / 市场三角化），反证搜索覆盖度随信封披露。",
  );
  sections.push(
    "## 3. 主张账本（按权重排列）\n\n"
    + claims
      .map((claim) => `- **${claim.text}** [${claim.weight}] — posterior ${claim.posterior} (${claim.verify_tier})`)
      .join("\n"),
  );
  sections.push(
    "## 4. 反证与让步\n\n"
    + (refuted.length > 0
      ? refuted.map((claim) => `- ${claim.text} — 被反证（posterior ${claim.posterior}）`).join("\n")
      : "- 无已驳回主张（反证搜索已执行，见搜索信封）"),
  );
  sections.push(
    `## 5. 信心与不确定性\n\n${ctx.confidence} — ${CONFIDENCE_NOTE[ctx.confidence]}。`
    + ` 什么证据会改变这个裁决：${mob.map((claim) => `${claim.text} 被驳回`).join("；") || "任一 make-or-break 主张被驳回"}。`,
  );
  sections.push(
    "## 6. 最便宜的下一步\n\n"
    + "以最小成本继续去险：对未决主张做一次低成本判别实验，或将 make-or-break 交由下游小流量试点。",
  );
  sections.push(
    "## 7. 三元裁决\n\n"
    + `证据说什么（无偏好）× 你的偏好与风险（你签的）→ **${ctx.verdict}**。`
    + (refusals.length > 0 ? `\n\n拒绝点：${refusals.join("；")}` : ""),
  );
  if (deleted.length > 0) {
    sections.push(`## 附：已删除产物（审计披露）\n\n${deleted.map((node) => `- ${node}`).join("\n")}`);
  }
  return sections.join("\n\n");
}

export function renderDeliverable(snapshot: RenderSnapshot, ctx: { verdict: string } & Record<string, unknown>): Deliverable {
  const claims = snapshot.claims ?? [];
  const supported = claims.filter((claim) => Number(claim.posterior) >= 0.9);
  const unverified = claims.filter((claim) => Number(claim.posterior) < 0.9 && Number(claim.posterior) > 0.1);
  const refuted = claims.filter((claim) => Number(claim.posterior) <= 0.1);
  const constraints = elementList(snapshot, "constraints");

  return {
    clarified_question: {
      requirements: elementList(snapshot, "requirements").map((r) => String(r.text)),
      refusals: elementList(snapshot, "refusals").map((r) => String(r.text)),
      verdict: ctx.verdict,
    },
    supported_claims: supported.map((claim) => ({
      text: String(claim.text),
      posterior: Number(claim.posterior),
      verify_tier: String(claim.verify_tier),
    })),
    unverified_assumptions: unverified.map((claim) => ({
      text: String(claim.text),
      reason: "single-source or below promotion threshold",
    })),
    refuted_and_disposition: refuted.map((claim) => ({
      text: String(claim.text),
      disposition: "refuted — 下游勿重踩",
    })),
    capability_outline: elementList(snapshot, "intents").map((intent) => String(intent.text)),
    constraints: {
      hard: constraints.filter((c) => c.hardness === "hard").map((c) => String(c.text)),
      guessed: constraints.filter((c) => c.hardness === "guessed").map((c) => String(c.text)),
    },
    deleted_nodes_disclosed: snapshot.deleted_nodes ?? [],
  };
}
