/** runPi tests (#670/#672/#676/#731): async execution over pi's RPC mode,
 * the settle-on-exit rule, process-group timeout kill, fixed isolated cwd,
 * and — new in #731 — STREAMING onDelta from thinking_delta events
 * (print mode buffered all stdout until exit: the streaming loss root cause).
 *
 * runPi speaks pi's rpc protocol; the stand-in "pi" is node running a fake
 * script that reads {type:"prompt"} from stdin and emits event lines. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { runPi } from "../src/pi-run.js";

const STREAM_PARTS = ["思考A。", "思考B。", "思考C。"];

/** rpc 协议模拟器主体：stdin 收 {type:"prompt"} → 流式 thinking_delta 事件 →
 * message_end（thinking+text 块）。variant 决定收尾行为。 */
function fakePiBody(variant: "stream" | "hang" | "sleep" | "cwd"): string {
  const onPrompt = `
  if (process.env.__NEVER__) {}
  const text = ${variant === "cwd" ? 'process.cwd()' : `'{"kind":"preference","reply":"最终回复"}'`};
  ${variant === "sleep" ? 'setTimeout(() => process.exit(0), 60_000); return;' : ""}
  const parts = ${JSON.stringify(STREAM_PARTS)};
  let acc = "";
  let i = 0;
  const timer = setInterval(() => {
    if (i < parts.length) {
      acc += parts[i];
      process.stdout.write(JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "thinking_delta", delta: parts[i], partial: { role: "assistant", content: [{ type: "thinking", thinking: acc }] } } }) + "\\n");
      i++;
      return;
    }
    clearInterval(timer);
    process.stdout.write(JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "thinking", thinking: acc }, { type: "text", text }] } }) + "\\n");
    ${variant === "hang" ? 'spawn(process.execPath, ["-e", "setTimeout(() => {}, 60_000)"], { stdio: "inherit" });' : ""}
    process.exit(0);
  }, 40);
`;
  return `
import { spawn } from "node:child_process";
let buf = "";
process.stdin.on("data", (c) => {
  buf += String(c);
  const nl = buf.indexOf("\\n");
  if (nl < 0) return;
  const cmd = JSON.parse(buf.slice(0, nl));
  if (cmd.type !== "prompt") { process.exit(1); }
  ${onPrompt}
});
`;
}

function makeFakePi(variant: "stream" | "hang" | "sleep" | "cwd"): string {
  const dir = mkdtempSync(join(tmpdir(), "rt-fake-pi-"));
  const script = join(dir, "fake-pi.mjs");
  writeFileSync(script, fakePiBody(variant));
  return script;
}

describe("runPi (#670/#672/#676/#731 rpc streaming)", () => {
  const fake = makeFakePi("stream");
  const fakeHang = makeFakePi("hang");
  const fakeSleep = makeFakePi("sleep");
  const fakeCwd = makeFakePi("cwd");

  it("rpc 流式：onDelta 收到逐段 thinking 增量，最终文本 = thinking+text 块拼接", async () => {
    const deltas: string[] = [];
    const t0 = Date.now();
    let firstDeltaAt: number | null = null;
    const out = await runPi(process.execPath, "测试 prompt", 15_000, [fake], (d) => {
      if (firstDeltaAt === null) firstDeltaAt = Date.now() - t0;
      deltas.push(d);
    });
    // 流式：多个增量、按序、第一个 delta 远早于退出（print 模式只在退出前一把 flush）
    expect(deltas).toEqual(STREAM_PARTS);
    expect(firstDeltaAt).not.toBeNull();
    expect(firstDeltaAt).toBeLessThan(3_000);
    // 最终文本与 print stdout 语义等价：thinking 块 + text 块顺序拼接
    expect(out).toBe(`思考A。思考B。思考C。{"kind":"preference","reply":"最终回复"}`);
  }, 20_000);

  it("settle-on-exit: a grandchild holding stdio cannot hang the runner (#676)", async () => {
    const t0 = Date.now();
    const out = await runPi(process.execPath, "测试 prompt", 15_000, [fakeHang]);
    expect(out).toContain("思考C。"); // settled at pi's own exit
    expect(Date.now() - t0).toBeLessThan(15_000); // not the grandchild's 60s
  }, 40_000);

  it("timeout SIGKILLs the whole process group with a typed error", async () => {
    await expect(runPi(process.execPath, "测试 prompt", 800, [fakeSleep])).rejects.toThrow(
      /terminated \(timeout/,
    );
  }, 10_000);

  it("spawn failure fails closed", async () => {
    await expect(runPi("/nonexistent/pi-binary", "x", 5_000, [])).rejects.toThrow(/pi spawn failed/);
  });

  it("cwd 隔离：pi 在固定的非仓库临时目录里跑，不继承仓库上下文（#706/#729）", async () => {
    // pi 会读启动目录向上找 AGENTS.md/项目上下文 —— runPi 必须在临时目录
    // 里 spawn，否则 research-tree 自己会被注入成"研究主题"。
    // #729：目录固定复用——pi 把 cwd 写进 system prompt 末尾，逐次换目录
    // 会打穿 DeepSeek context caching 的最前缀。
    const out1 = await runPi(process.execPath, "测试 prompt", 15_000, [fakeCwd]);
    const out2 = await runPi(process.execPath, "测试 prompt", 15_000, [fakeCwd]);
    // 固定路径（无 mkdtemp 随机后缀）且两次一致
    expect(out1).toMatch(/rt-pi-cwd/);
    expect(out1).not.toMatch(/rt-pi-cwd-/);
    expect(out1).toBe(out2);
    expect(out1).not.toContain("research-tree");
    expect(out1).not.toContain("webui-server");
  }, 20_000);
});
