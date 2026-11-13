/** Async pi runner (issue #670, perf #672, settle fix #676).

spawnSync froze the entire Node event loop for the full duration of every
pi call (45s+) — the whole WebUI hung: every HTTP/WS request queued behind
one synchronous spawn. runPi spawns **asynchronously**, keeps the event
loop free, enforces a hard timeout, and fails closed with the process's
own output in the message so the existing parse layers keep working.

#672: server-side structured calls (classification / turn / extraction)
pass extraArgs `["-nt"]` — they need TEXT JSON only, and skipping the
tool/extension tool-surface cuts latency ~3x on machines with the default
extension pack (measured 60s → 18s for a classification).

**#676 settle-on-exit rule**: pi extensions spawn MCP children that
inherit the runner's stdio pipes — Node's `close` event waits for ALL pipe
writers and NEVER fires when a grandchild outlives pi. runPi therefore
settles on **`exit`** (the pi process itself is done) and takes whatever
stdout has accumulated, and kills the whole process GROUP on timeout
(SIGKILL — extensions ignore SIGTERM).
*/

import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export class PiRunError extends Error {}

export function runPi(
  command: string,
  prompt: string,
  timeoutMs = 300_000,
  extraArgs: string[] = [],
  /** streaming hook: fires per stdout chunk as the model generates (#679) */
  onDelta?: (delta: string) => void,
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    // cwd 隔离（#706 商业化审计）：server 从仓库目录启动时，pi 会向上读
    // AGENTS.md / 项目上下文，把 research-tree 自己当成研究主题注入回答
    // ——结构化调用（turn/extraction/classification）必须在一无所有的
    // 临时目录里跑。每个调用独立临时目录，进程退出后由 OS 清理。
    const isolatedCwd = mkdtempSync(join(tmpdir(), "rt-pi-cwd-"));
    // detached: own process group — lets the timeout SIGKILL the whole tree
    // (pi + its MCP grandchildren), not just pi
    const child = spawn(command, [...extraArgs, "-p", prompt], {
      detached: true,
      cwd: isolatedCwd,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    let settled = false;
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      try {
        if (child.pid !== undefined) {
          process.kill(-child.pid, "SIGKILL"); // whole group
        }
      } catch {
        child.kill("SIGKILL");
      }
    }, timeoutMs);

    const settle = (error?: Error): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error !== undefined) {
        reject(error);
      } else {
        resolve(out);
      }
    };

    child.stdout?.on("data", (chunk) => {
      const text = String(chunk);
      out += text;
      if (onDelta !== undefined && text !== "") {
        onDelta(text);
      }
    });
    child.on("error", (error) => {
      settle(new PiRunError(`pi spawn failed: ${String(error)}`));
    });
    // settle on EXIT (pi itself is done) — never on `close`, which waits for
    // inherited stdio pipes held by outliving extension children
    child.on("exit", (code, signal) => {
      if (timedOut) {
        settle(
          new PiRunError(
            `pi was terminated (timeout ${Math.round(timeoutMs / 1000)}s) — extensions may still be loading or the network is slow; retry`,
          ),
        );
        return;
      }
      if (signal !== null) {
        settle(new PiRunError(`pi was killed by signal ${signal}`));
        return;
      }
      if (code === 0) {
        settle();
      } else {
        settle(new PiRunError(`pi exited with code ${code}: ${out.slice(0, 200)}`));
      }
    });
  });
}
