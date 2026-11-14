/** LLM prompt-caching prefix stability (issue #729).

DeepSeek context caching hits on the longest shared request prefix. The
system prompt (pi appends `Current working directory: …`) is the FIRST
prefix — any per-call variation there (mkdtemp cwd) forks every request at
token one. Same law applies to the prompt body: stable boilerplate first,
per-call payload LAST. These tests pin that structure so it cannot
regress silently. */

import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { buildArbiterPrompt } from "../src/graph_arbiter.js";
import { buildTurnPrompt, type TranscriptMessage } from "../src/chat-turn.js";
import { piIsolatedCwd } from "../src/pi-run.js";
import { buildSynthPrompt } from "../src/research_worker.js";

function sharedPrefixLength(a: string, b: string): number {
  let i = 0;
  const n = Math.min(a.length, b.length);
  while (i < n && a[i] === b[i]) i++;
  return i;
}

function msg(seq: number, role: string, kind: string, text: string): TranscriptMessage {
  return { seq, role, kind, text, created_at: "t" };
}

describe("prompt prefix stability (#729 caching)", () => {
  it("runPi 的隔离 cwd 跨调用稳定（mkdtemp 每次换目录打穿 system prompt 前缀）", () => {
    const a = piIsolatedCwd();
    const b = piIsolatedCwd();
    expect(a).toBe(b);
    expect(a.startsWith(tmpdir())).toBe(true);
    // 隔离语义：目录存在（幂等 mkdir 由调用方/首次取用保证）、非仓库子路径
    expect(existsSync(a)).toBe(true);
    expect(a).not.toContain("research-tree");
  });

  it("arbiter prompt：wave 间在『当前图状态』之前逐字节一致（规则段不被 wave 号推出前缀）", () => {
    const question = "verify: 现有应用在 2C4G 配置上足以稳定运行";
    const branches = ["部署", "成本"];
    const nodes = [
      { stage_id: "t/stage-1", title: "深挖｜负载基线", status: "complete", findings: "发现A" },
    ];
    const wave1 = buildArbiterPrompt(question, branches, nodes, 1);
    const wave2 = buildArbiterPrompt(
      question,
      branches,
      [
        ...nodes,
        { stage_id: "t/stage-2", title: "验证｜升级效果", status: "pending", findings: null },
      ],
      2,
    );
    const fork = Math.min(wave1.indexOf("当前图状态"), wave1.length);
    expect(fork).toBeGreaterThan(0);
    // wave 段之前的全部内容（模板+规则+JSON 指令+问题+分支）是共同前缀
    expect(wave1.slice(0, fork)).toBe(wave2.slice(0, fork));
    // wave 号不得出现在该稳定前缀里
    expect(wave1.slice(0, fork)).not.toContain("wave");
    // 共享前缀足够长（缓存才有收益）——规则段必须在前缀内
    expect(wave1.slice(0, fork)).toContain("有向无环");
    expect(wave1.slice(0, fork)).toContain("只输出 JSON");
  });

  it("综合员 prompt：不同检索词/来源在检索词之前逐字节一致（任务级上下文共享）", () => {
    const claims = ["命题A"];
    const upstream = "上游：阶段1 发现X";
    const a = buildSynthPrompt("query-one", claims, upstream, [
      { title: "来源1", snippet: "s1" },
    ]);
    const b = buildSynthPrompt("完全不同的检索词X", claims, upstream, [
      { title: "来源2", url: "https://x", snippet: "s2" },
    ]);
    const k = sharedPrefixLength(a, b);
    expect(k).toBeGreaterThan(200); // 规则+输出格式+命题+上游发现全部共享
    expect(a.slice(0, k)).toContain("只输出 JSON");
    expect(a.slice(0, k)).toContain("上游：阶段1");
    expect(a.slice(k)).toContain("query-one");
    expect(b.slice(k)).toContain("完全不同的检索词X");
  });

  it("chat.turn prompt：transcript 只增不改时旧 prompt 是新 prompt 的前缀（守护防回归）", () => {
    const short = buildTurnPrompt([msg(1, "user", "preference", "想开数据标注公司")]);
    const long = buildTurnPrompt([
      msg(1, "user", "preference", "想开数据标注公司"),
      msg(2, "rt", "reply", "复述核心诉求……"),
      msg(3, "user", "claim", "都能拿到"),
    ]);
    expect(long.startsWith(short)).toBe(true);
  });
});
