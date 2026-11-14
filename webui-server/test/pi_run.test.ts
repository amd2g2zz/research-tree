/** runPi tests (issues #670/#672/#676): async execution, event-loop freedom,
 * the settle-on-exit rule (grandchild holding stdio), and process-group
 * timeout kill.
 *
 * runPi runs `<command> [-nt] -p <prompt>` — the stand-in "pi" is node
 * itself and the prompt is a JS EXPRESSION (-p evaluates it). */

import { describe, expect, it } from "vitest";

import { runPi } from "../src/pi-run.js";

describe("runPi (#670/#672/#676)", () => {
  it("resolves stdout on success", async () => {
    const out = await runPi(process.execPath, "40 + 2", 15_000, []);
    expect(out.trim()).toBe("42");
  });

  it("settle-on-exit: a grandchild holding stdio cannot hang the runner (#676)", async () => {
    const t0 = Date.now();
    // the expression prints its answer, spawns a GRANDCHILD that inherits
    // stdio and lives 60s, then exits — close never fires; exit must settle
    const expr =
      "(function(){ process.stdout.write('answer-42');" +
      "require('node:child_process').spawn(process.execPath, ['-e', 'setTimeout(() => {}, 60_000)'], { stdio: 'inherit' });" +
      "setTimeout(() => process.exit(0), 200); })()";
    const out = await runPi(process.execPath, expr, 30_000, []);
    expect(out).toContain("answer-42"); // settled at pi's own exit
    expect(Date.now() - t0).toBeLessThan(15_000); // not the grandchild's 60s
  }, 40_000);

  it("timeout SIGKILLs the whole process group with a typed error", async () => {
    await expect(runPi(process.execPath, "setTimeout(() => {}, 60_000)", 800, [])).rejects.toThrow(
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
    // 会打穿 DeepSeek context caching 的最前缀（结构性 0% 命中）。
    const expr = "process.stdout.write(process.cwd())";
    const out1 = await runPi(process.execPath, expr, 15_000, []);
    const out2 = await runPi(process.execPath, expr, 15_000, []);
    // 固定路径（无 mkdtemp 随机后缀）且两次一致；"true" 是 -p 打印的表达式返回值
    expect(out1).toMatch(/rt-pi-cwd/);
    expect(out1).not.toMatch(/rt-pi-cwd-/);
    expect(out1).toBe(out2);
    expect(out1).not.toContain("research-tree");
    expect(out1).not.toContain("webui-server");
  });
});
