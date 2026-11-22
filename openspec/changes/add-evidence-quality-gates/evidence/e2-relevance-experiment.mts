/** E2 实验（issue #744，计划 §8-E2）：相关性判定两方案在确定性黄金集上的
 * 对比。黄金集：医院研究任务 × {医院相关源, 游戏源, 太空源, 音频转录源,
 * 空结果}——取材 dogfood ISSUE-004 真实失真样本。
 *
 * 方案 a) 启发式打分（classifySourceRelevance，纯函数，零调用成本）
 * 方案 b) pi 单批判定（结构化 prompt 输出 verdict+basis，真实 pi 二进制采样）
 *
 * 运行：node --experimental-strip-types e2-relevance-experiment.mts
 * 输出：markdown 数据表（逐案 verdict/延迟/准确率）→ design.md 引用。
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";

import { classifySourceRelevance } from "../../../../webui-server/src/relevance.ts";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(here, "../../../../webui-server/test/fixtures/golden-relevance");

interface Fixture {
  case: string;
  query: string;
  claims: string[];
  sources: Array<{ title: string; url?: string; snippet?: string }>;
  golden: { labels: string[]; sufficiency: string };
}

const files = readdirSync(fixturesDir).filter((f) => f.endsWith(".json")).sort();
const fixtures = files.map((f) => JSON.parse(readFileSync(join(fixturesDir, f), "utf8")) as Fixture);

// ── 方案 a：启发式 ──────────────────────────────────────────────
console.log("## 方案 a) 启发式打分（bigram 重叠，纯函数）\n");
console.log("| case | 逐来源 verdict（golden→实测） | 延迟 | 源级准确率 |");
console.log("|---|---|---|---|");
let totalSources = 0;
let correctSources = 0;
for (const fx of fixtures) {
  const t0 = performance.now();
  const verdicts = classifySourceRelevance({ query: fx.query, claims: fx.claims }, fx.sources);
  const elapsed = performance.now() - t0;
  const cell = fx.sources
    .map((s, i) => {
      const g = fx.golden.labels[i] ?? "?";
      const v = verdicts[i]!.verdict;
      const ok = g === v;
      if (fx.golden.labels.length > 0) {
        totalSources += 1;
        if (ok) correctSources += 1;
      }
      return `${g.slice(0, 4)}→${v.slice(0, 4)}${ok ? "✓" : `✗(${verdicts[i]!.score.toFixed(2)})`}`;
    })
    .join("、");
  const acc =
    fx.golden.labels.length > 0
      ? `${(fx.sources.filter((_, i) => fx.golden.labels[i] === verdicts[i]!.verdict).length / fx.sources.length) * 100 | 0}%`
      : "—";
  console.log(`| ${fx.case} | ${cell} | ${elapsed.toFixed(2)}ms | ${acc} |`);
}
if (totalSources > 0) {
  console.log(`\n启发式源级准确率：${correctSources}/${totalSources} = ${((correctSources / totalSources) * 100).toFixed(1)}%`);
}

// ── 方案 b：pi 单批判定（真实采样） ─────────────────────────────
const PI = join(process.env.HOME ?? "", ".pi/agent/npm/node_modules/.bin/pi");
const { runPi } = await import("../../../../webui-server/src/pi-run.ts");

function buildVerdictPrompt(fx: Fixture): string {
  return (
    "你是研究来源相关性判定员。给定研究命题与检索结果，对每条来源判定它与命题的关系。\n" +
    "规则：\n" +
    "1. 只依据资料本身，不得编造；\n" +
    "2. verdict 三选一：relevant（与命题直接相关）/ uncertain（无法确定）/ irrelevant（与命题无关）；\n" +
    "3. 每条 verdict 附一句话 basis（依据资料的哪部分）；\n" +
    "4. 同时给出总体判断 sufficiency：sufficient / insufficient / conflicted，并列出 unresolvedClaims（未能回答的命题）。\n" +
    '只输出 JSON：{"verdicts":[{"index":1,"verdict":"irrelevant","basis":"一句话依据"}],"sufficiency":"insufficient","unresolvedClaims":["..."]}\n' +
    "\n【本次判定输入】\n" +
    "命题：" +
    fx.claims.join("；") +
    "\n检索词：" +
    fx.query +
    "\n检索结果：\n" +
    fx.sources
      .map((s, i) => `${i + 1}. ${s.title}${s.snippet ? ` — ${s.snippet}` : ""}`)
      .join("\n") +
    "\n"
  );
}

console.log("\n## 方案 b) pi 单批判定（真实采样）\n");
console.log("| case | 逐来源 verdict（golden→实测） | 延迟 | usage | 源级准确率 |");
console.log("|---|---|---|---|---|");
let piTotal = 0;
let piCorrect = 0;
for (const fx of fixtures) {
  if (fx.sources.length === 0) {
    console.log(`| ${fx.case} | —（空结果机械判定，无判定调用） | — | — | — |`);
    continue;
  }
  const t0 = performance.now();
  try {
    const stdout = await runPi(PI, buildVerdictPrompt(fx), 300_000, ["-nt", "-ne", "--no-session", "--no-skills"]);
    const elapsed = performance.now() - t0;
    const m = /\{[\s\S]*\}/.exec(stdout);
    const parsed = m !== null ? (JSON.parse(m[0]) as { verdicts?: Array<{ index: number; verdict: string }>; usageLog?: string }) : null;
    const verdicts = parsed?.verdicts ?? [];
    const cell = fx.sources
      .map((s, i) => {
        const g = fx.golden.labels[i] ?? "?";
        const v = verdicts.find((x) => x.index === i + 1)?.verdict ?? "MISSING";
        if (fx.golden.labels.length > 0) {
          piTotal += 1;
          if (g === v) piCorrect += 1;
        }
        return `${g.slice(0, 4)}→${v.slice(0, 4)}${g === v ? "✓" : "✗"}`;
      })
      .join("、");
    console.log(`| ${fx.case} | ${cell} | ${(elapsed / 1000).toFixed(1)}s | 见 pi-run 日志 | ${
      fx.golden.labels.length > 0 ? `${(fx.sources.filter((_, i) => fx.golden.labels[i] === verdicts.find((x) => x.index === i + 1)?.verdict).length / fx.sources.length) * 100 | 0}%` : "—"
    } |`);
  } catch (error) {
    console.log(`| ${fx.case} | PI-FAILED：${String(error).slice(0, 80)} | — | — | — |`);
  }
}
if (piTotal > 0) {
  console.log(`\npi 单批判定源级准确率：${piCorrect}/${piTotal} = ${((piCorrect / piTotal) * 100).toFixed(1)}%`);
}
