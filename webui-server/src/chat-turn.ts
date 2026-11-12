/** chat.turn — the conversational loop (issue #660, WebUI v3 step 1, docs
 * product/05 §1).

The A1 strategies (四分路由, 歧视性提问, 约束溯源, 收敛判定) are engine-side
and built-in — but until now the UI only showed routing receipts, so the
user was talking at a wall. chat.turn makes the agent SPEAK:

- builds a structured prompt from the transcript + engine state, demanding a
  strict JSON turn: {reply, questions[], recon?};
- **reply**: a substantive response (restate understanding, name gaps, state
  the next step) — never a bare receipt;
- **questions[]**: proactive clarifying questions (歧视性提问: deployment
  fact vs subjective estimate; missing kill conditions; budget/scope);
- **recon**: optional early reconnaissance — a search query executed for
  real through the DataSourceProvider port (anysearch), results folded back
  into the conversation as data.

Everything lands in chat_messages (reply/question/recon are data). The
classification receipt (#651) is untouched and parallel. Fail-closed: no
keyed session, unusable model output, or provider failure → typed error,
never a guessed reply.
*/

import type { DataSourceProvider } from "../../rt-core/src/providers/types.js";

export interface TranscriptMessage {
  seq: number;
  role: string;
  kind: string;
  text: string;
  created_at: string;
}

export type TurnKind = "preference" | "claim" | "guess" | "constraint" | "branch";

export interface TurnOutput {
  /** the utterance's semantic kind — judged in the SAME pi call (issue #674:
   * one call per turn instead of classify-then-respond) */
  kind: TurnKind;
  /** model-judged: is the idea concrete enough to enter the mindmap
   * confirmation stage? (#679 — drives the in-stream action card) */
  converged: boolean;
  reply: string;
  /** 自动 planning（用户裁定 2026-11-13）：当前研究计划草案——首轮即产出，
   * 后续轮次更新；空数组 = 结构尚未成形 */
  plan: string[];
  questions: string[];
  recon?: { query: string; kind?: string } | null;
}

export interface TurnResult extends TurnOutput {
  recon_results?: Array<{ title: string; url?: string; snippet?: string }>;
}

export function buildTurnPrompt(messages: TranscriptMessage[]): string {
  const transcript = messages
    .filter((m) => m.role === "user" || m.role === "rt")
    .map((m) => `[${m.seq}][${m.role}] ${m.text}`)
    .join("\n");
  return (
    "你是 rt（研究台）的对齐助手：根据用户意图与情景**自动推进**研究对齐，而不是反复盘问。\n" +
    "规则：\n" +
    '1. 判定最后一句话的语义类型 kind ∈ preference|claim|guess|constraint|branch（偏好意图/可判定主张/方案猜测/硬约束/分支岔路）。\n' +
    "2. reply 给实质回应：复述你理解的核心诉求、指出虚/缺的部分、说明本轮做了什么、下一步是什么。语气推进，不敷衍。\n" +
    "3. **plan = 当前研究计划草案**（3-5 条，每条一个可执行的调研动作/待验证命题）。首轮就给出初步计划（基于合理假设，标注假设处），后续轮次随新信息修订。plan 是主动产出，不是等用户问。\n" +
    "4. 提问克制：只有当某个缺口**不补就无法推进**时才问（每轮最多 2 个，优先本轮最重要的一个；之前已经问过的问题绝不重复）；没有关键缺口就给空数组——用 plan 和 recon 推进代替提问。\n" +
    "5. 情景合适就主动调用工具：给出 recon（{\"query\":\"搜索词\"}）做一次真实资料搜索帮助澄清；否则 null。\n" +
    "6. converged：想法已具体到可开始调研（对象/范围/可验证口径齐备）时 true——宁缺毋滥，一两句话不足以成形时保持 false。\n" +
    '只输出 JSON：{"kind":"...","converged":false,"reply":"...","plan":["..."],"questions":["..."],"recon":null}\n\n对话：\n' +
    transcript
  );
}

export function parseTurnOutput(stdout: string): TurnOutput {
  const match = /\{[\s\S]*\}/.exec(stdout);
  if (match === null) {
    throw new Error("turn returned no JSON object");
  }
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(match[0]) as Record<string, unknown>;
  } catch {
    throw new Error(`turn returned malformed JSON: ${match[0].slice(0, 60)}`);
  }
  const kind = raw.kind;
  const KINDS = ["preference", "claim", "guess", "constraint", "branch"];
  if (typeof kind !== "string" || !KINDS.includes(kind)) {
    throw new Error(`turn returned an unusable kind: ${JSON.stringify(kind)}`);
  }
  const converged = raw.converged === true;
  const reply = raw.reply;
  if (typeof reply !== "string" || reply.trim() === "") {
    // a turn without a substantive reply is the wall we are removing
    throw new Error("turn returned no substantive reply");
  }
  const plan = Array.isArray(raw.plan)
    ? (raw.plan.filter((s) => typeof s === "string" && s.trim() !== "") as string[])
    : [];
  const questions = Array.isArray(raw.questions)
    ? (raw.questions.filter((q) => typeof q === "string" && q.trim() !== "") as string[])
    : [];
  const reconRaw = raw.recon;
  const recon =
    typeof reconRaw === "object" && reconRaw !== null && typeof (reconRaw as Record<string, unknown>).query === "string"
      ? { query: (reconRaw as Record<string, unknown>).query as string, kind: "search" }
      : null;
  return { kind: kind as TurnKind, converged, reply, plan, questions, recon };
}

/** Execute the recon through the DataSourceProvider port (real search). */
export async function runRecon(
  provider: DataSourceProvider,
  query: string,
): Promise<Array<{ title: string; url?: string; snippet?: string }>> {
  const results = await provider.search({ query });
  return results.slice(0, 5).map((r) => ({ title: String(r.title ?? ""), url: r.url, snippet: r.snippet }));
}

/** Fold recon results into a data line for the transcript. */
export function reconToText(results: Array<{ title: string; url?: string; snippet?: string }>): string {
  if (results.length === 0) {
    return "侦查无结果。";
  }
  // numbered citations with URLs (#679: 1、2、3… 引用带链接)
  return `前期侦查（${results.length} 条来源）：` + results.map((r, i) => `${i + 1}. ${r.title}${r.url ? `（${r.url}）` : ""}${r.snippet ? ` — ${r.snippet}` : ""}`).join("；");
}
