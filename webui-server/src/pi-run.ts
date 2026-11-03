/** Async pi runner (issue #670, perf #672).

spawnSync froze the entire Node event loop for the full duration of every
pi call (45s+ with a reasoning model and extensions) — the whole WebUI
hung: every HTTP/WS request queued behind one synchronous spawn. runPi
spawns **asynchronously** (promise wrapper), keeps the event loop free,
enforces a hard timeout (kill + typed error — a hung pi must not hang the
server forever), and fails closed with the process's own output in the
message so the existing parse layers keep working.

#672: server-side structured calls (classification / turn / extraction)
pass extraArgs `["-nt"]` — they need TEXT JSON only, and skipping the
tool/extension tool-surface cuts latency ~3x on machines with the default
extension pack (measured 60s → 18s for a classification).
*/

import { spawn } from "node:child_process";

export class PiRunError extends Error {}

export function runPi(
  command: string,
  prompt: string,
  timeoutMs = 300_000,
  extraArgs: string[] = [],
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const child = spawn(command, [...extraArgs, "-p", prompt], { timeout: timeoutMs });
    let out = "";
    let settled = false;
    child.stdout?.on("data", (chunk) => {
      out += String(chunk);
    });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      reject(new PiRunError(`pi spawn failed: ${String(error)}`));
    });
    child.on("close", (code, signal) => {
      if (settled) return;
      settled = true;
      if (code === 0) {
        resolve(out);
      } else if (signal !== null) {
        // timeout kill (or external signal): extensions can still be loading
        reject(new PiRunError(`pi was terminated (${signal}) — extensions may still be loading or the network is slow; retry`));
      } else {
        reject(new PiRunError(`pi exited with code ${code}: ${out.slice(0, 200)}`));
      }
    });
  });
}
