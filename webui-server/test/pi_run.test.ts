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
});
