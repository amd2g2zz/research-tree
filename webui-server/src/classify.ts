/** Keyed-session readiness + hub utterance auto-classification (issue #651).

LLM 产生判断（分类），判断落盘为数据后由算法统治：the mechanical four-way
router (#555) stays engine-side — only the utterance KIND is judged. The
kind comes from a ClassificationPort with two strategies:

- **PiSessionClassifier** — spawns the pi binary headless with a structured
  prompt and parses strict JSON out; only selectable when a keyed session is
  ready (auth key + default model, per #638's single source).
- **HeuristicClassifier** — deterministic keyword rules, disclosed as a
  fallback (never presented as LLM judgment).

Red lines: an explicit user kind is always respected (classified_by=user);
classification failure fails CLOSED (throws, no guessed kind); every
receipt/transcript records classified_by so nothing pretends to be automatic.
*/

import { runPi } from "./pi-run.js";

export type UtteranceKind = "preference" | "claim" | "guess" | "constraint" | "branch";
export type ClassifiedBy = "user" | "pi-session" | "heuristic";

export interface Classification {
  kind: UtteranceKind;
  classified_by: ClassifiedBy;
}

export interface ClassifierPort {
  readonly name: Exclude<ClassifiedBy, "user">;
  classify(text: string): Promise<Classification>;
}

export const UTTERANCE_KINDS: readonly UtteranceKind[] = ["preference", "claim", "guess", "constraint", "branch"];

/** Deterministic fallback — honest about being rules, never LLM judgment. */
export class HeuristicClassifier implements ClassifierPort {
  readonly name = "heuristic" as const;

  async classify(text: string): Promise<Classification> {
    return { kind: heuristicKind(text), classified_by: "heuristic" };
  }
}

function has(text: string, ...words: string[]): boolean {
  return words.some((w) => text.includes(w));
}

function heuristicKind(text: string): UtteranceKind {
  if (has(text, "或者", "换个", "要么", "分支", "另一条路", "？")) {
    return "branch";
  }
  if (has(text, "吧", "大概", "应该够", "估计", "猜")) {
    return "guess";
  }
  if (has(text, "希望", "我要", "越快越好", "优先", "偏好")) {
    return "preference";
  }
  if (has(text, "必须", "只能", "硬性", "部署在")) {
    return "constraint";
  }
  return "claim"; // statements default to the claim ledger (检验：不信不驳)
}

/** pi headless session — only when keyed. The runner is injectable for
 * contract tests (CI never spawns a real pi). */
export class PiSessionClassifier implements ClassifierPort {
  readonly name = "pi-session" as const;

  constructor(
    private readonly options: { command?: string; runner?: (command: string, prompt: string) => string | Promise<string>; timeoutMs?: number } = {},
  ) {}

  async classify(text: string): Promise<Classification> {
    const prompt =
      "将下面这句话分类为 preference|claim|guess|constraint|branch 之一。" +
      "只输出 JSON：{\"kind\":\"...\"}。句子：" +
      JSON.stringify(text);
    const command = this.options.command ?? "pi";
    // async spawn (issue #670): never block the event loop; hard timeout —
    // a hung pi fails closed instead of freezing the whole WebUI
    const stdout = await (this.options.runner ?? ((cmd, p) => runPi(cmd, p, this.options.timeoutMs ?? 300_000, ["-nt"])))(
      command,
      prompt,
    );
    const parsed = this.parse(stdout);
    if (!UTTERANCE_KINDS.includes(parsed)) {
      // fail closed: a pi answer we cannot trust is NOT silently rerouted
      throw new Error(`pi-session classification returned an unusable kind: ${JSON.stringify(parsed)}`);
    }
    return { kind: parsed, classified_by: "pi-session" };
  }

  /** Strict JSON extraction — the model may wrap it in prose. */
  private parse(stdout: string): UtteranceKind {
    const match = /\{[^}]*\}/.exec(stdout);
    if (match === null) {
      throw new Error("pi-session classification returned no JSON object");
    }
    try {
      return (JSON.parse(match[0]) as { kind?: string }).kind as UtteranceKind;
    } catch {
      throw new Error("pi-session classification returned malformed JSON");
    }
  }
}

/** Strategy selection keyed on the #638 single-source readiness probe. */
export function pickClassifier(ready: { ready: boolean }, options: ConstructorParameters<typeof PiSessionClassifier>[0] = {}): ClassifierPort {
  return ready.ready ? new PiSessionClassifier(options) : new HeuristicClassifier();
}
