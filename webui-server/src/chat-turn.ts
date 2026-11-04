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
    "你是 rt（研究台）的对齐助手，负责在调研开始前把用户的想法从虚变实。\n" +
    "规则：\n" +
    '1. 先判定最后一句话的语义类型 kind ∈ preference|claim|guess|constraint|branch（偏好意图/可判定主张/方案猜测/硬约束/分支岔路）。\n' +
    "2. reply 必须给实质回应：复述你理解的核心诉求、指出目前想法里虚/缺的部分、说明下一步——绝不能只复述原话。\n" +
    "3. 仅当存在影响调研方向的关键缺口时才提问（0-3 个，歧视性优先：部署事实还是主观估计？缺什么验收/kill 条件？预算和范围？）；没有关键缺口就给空数组——不为问而问。\n" +
    "4. 如果做一次简单资料搜索能让问题更清晰，给出 recon（{\"query\":\"搜索词\"}）；否则为 null。\n" +
    "5. converged：判断想法是否已具体到可以开始调研（有明确的对象/范围/可验证的口径）；已成形=true，仍虚=false。\n" +
    '只输出 JSON：{"kind":"...","converged":false,"reply":"...","questions":["..."],"recon":null}\n\n对话：\n' +
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
  const questions = Array.isArray(raw.questions)
    ? (raw.questions.filter((q) => typeof q === "string" && q.trim() !== "") as string[])
    : [];
  const reconRaw = raw.recon;
  const recon =
    typeof reconRaw === "object" && reconRaw !== null && typeof (reconRaw as Record<string, unknown>).query === "string"
      ? { query: (reconRaw as Record<string, unknown>).query as string, kind: "search" }
      : null;
  return { kind: kind as TurnKind, converged, reply, questions, recon };
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
